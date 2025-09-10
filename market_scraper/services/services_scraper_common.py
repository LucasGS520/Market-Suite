""" Funções e utilidades compartilhadas entre os scrapers

Responsável apenas por obter e interpretar o HTML dos produtos.
Qualquer persistência de dados ou autenticação deve ser tratada
por camadas externas, como o módulo ``market_alert``. Também
realiza o pré-processamento dos dados, tratamento de status
especiais (bloqueios e ``NOT_MODIFIED``) e integração com cache.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import asyncio
from urllib.parse import urlparse

from fastapi import HTTPException, status
import structlog

from market_scraper.utils.constants import to_mobile_url
from market_scraper.utils.http_utils import extract_hostname
from market_scraper.utils.intelligent_cache import IntelligentCacheManager
from market_scraper.utils.http_cache import get_cache_headers
from market_scraper.utils.rate_limiter import RateLimiter
from market_scraper.utils.circuit_breaker import CircuitBreaker
from market_scraper.utils.block_recovery import BlockRecoveryManager
from market_scraper.utils.robots_txt import RobotsTxtParser
from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager
from market_scraper.utils.data_quality_validator import DataQualityValidator

from shared.enums import BlockResult
from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping

from market_scraper.services.domain_policy import strategies_for
from market_scraper.services.multi_strategy_orchestrator import MultiStrategyScraperOrchestrator


#Logger estruturado para registrar o fluxo do scraping
logger = structlog.get_logger("scraper_common")

#Gerenciador de cache inteligente para produtos
cache_manager = IntelligentCacheManager()

#Gerenciador de user-agent para consultas ao robots.txt
ua_manager = IntelligentUserAgentManager()

#Validador simples de campos essenciais do scraping
validator = DataQualityValidator()

async def scrape_product_common_async(
    *,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping | CompetitorProductCreateScraping,
    product_type: Literal["monitored", "competitor"],
    rate_limiter:RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    recovery_manager: BlockRecoveryManager | None = None,
) -> dict:
    """ Seleciona e executa a estratégia adequada para a URL

    A URL é normalizada para um formato canônico (mobile) antes de
    consultar o cache e disparar as estratégias. A função delega a
    lógica de seleção e execução para o :class:`MultiStrategyScraperOrchestrator`
    que também valida os dados obtidos e registra métricas de fallback
    entre estratégias. Após o scraping, os campos essenciais são
    verificados novamente para garantir consistência. Quando o scraping
    é bem-sucedido, os dados são armazenados no ``IntelligentCacheManager``
    e, quando disponíveis, os cabeçalhos ``ETag``/``Last-Modified`` do
    ``http_cache`` também são salvos para evitar requisições desnecessárias
    no futuro. O cache é reaproveitado apenas quando contém os campos
    essenciais ``name`` e ``current_price`` e passa pela validação do
    ``DataQualityValidator``. Em casos de erro o retorno sempre inclui o
    campo ``detail`` explicando o motivo de falha. Quando o servidor
    responde com ``NOT_MODIFIED`` o status é repassado diretamente e os
    dados do cache são anexados quando existentes.
    """
    #Registra o início do fluxo de scraping
    logger.info("start_scraping", url=url, product_type=product_type)

    #Converte a URL para formato canônico (mobile) para evitar variações
    normalized_url = to_mobile_url(url)
    marketplace = extract_hostname(normalized_url)

    #Verifica diretivas de robots.txt antes de prosseguir
    parser = RobotsTxtParser(base_url=normalized_url)
    user_agent = ua_manager.get_user_agent("scraper_common")
    path = urlparse(normalized_url).path or "/"
    #Aborta com HTTP 403 quando o caminho não é permitido
    if not await parser.is_allowed(path, user_agent):
        logger.warning("blocking_robots", url=normalized_url, user_agent=user_agent)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bloqueado pelo robots.txt",
        )
    #Respeita o crawl-delay recomendado pelo site
    delay = await parser.get_crawl_delay(user_agent)
    if delay:
        logger.info("waiting_crawl_delay", delay=delay)
        await asyncio.sleep(delay)

    #Verifica se já existe conteúdo cacheado para a URL normalizada e o marketplace
    logger.info("checking_cache", url=normalized_url)
    cached = cache_manager.get(marketplace=marketplace, url=normalized_url)
    if cached:
        logger.info("cache_found", url=normalized_url)
        #Quando o valor armazenado possui campos auxiliares, retorna apenas os dados
        details = cached.get("data", cached)
        try:
            validator.validate(details)
        except ValueError as err:
            logger.info("cache_invalid", url=normalized_url, reason=str(err))
        else:
            logger.info("cache_used", url=normalized_url)
            return {"status": "success", "details": details}
    else:
        logger.info("cache_not_found", url=normalized_url)

    orchestrator = MultiStrategyScraperOrchestrator(strategy_selector=strategies_for)
    logger.info("running_orchestrator", url=normalized_url)
    try:
        result = await orchestrator.scrape(
            url=normalized_url,
            user_id=user_id,
            payload=payload,
            product_type=product_type,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            recovery_manager=recovery_manager,
        )
    except Exception as err:
        logger.exception("orchestrator_exception", url=normalized_url, error=str(err))
        return {"status": "error", "detail": f"Erro interno no scraping: {err}"}
    status_result = result.get("status")
    details = result.get("details")
    logger.info("return_orchestrator", status=status_result)
    if status_result == "success":
        if not details:
            logger.error("missing_details", url=normalized_url)
            return {"status": "error", "detail": "Dados do produto ausentes"}
        try:
            #Garante que os campos essenciais estejam corretos
            validator.validate(details)
        except ValueError as err:
            #Retorna erro informando o campo ausente ou inválido
            logger.error("validation_failed", erro=str(err), url=normalized_url)
            return {"status": "error", "detail": str(err)}
 
        #Inclui cabeçalhos de ETag/Last-Modified para requisições condicionais futuras apenas se houverem valores válidos
        headers_cache = get_cache_headers(normalized_url)
        cache_value = {"data": details}
        if headers_cache.get("etag") or headers_cache.get("last_modified"):
            cache_value["headers"] = headers_cache
        cache_manager.set(
            marketplace=marketplace,
            url=normalized_url,
            value=cache_value,
        )
        logger.info("stored_cache", url=normalized_url)
        logger.info("scraping_success", url=normalized_url)
        return {"status": "success", "details": details}
    
    if status_result == "NOT_MODIFIED":
        #Quando o servidor indica que o recurso não mudou, não há necessidade de processar o resultado. Caso exista um valor cacheado ele é anexado ao retorno apenas para fins informativos.   
        logger.info("content_not_modified", url=normalized_url)
        cached = cache_manager.get(marketplace=marketplace, url=normalized_url)
        if cached:
            logger.info("content_not_modified", url=normalized_url)
            return {"status": "NOT_MODIFIED", "details": cached}
        return {"status": "NOT_MODIFIED"}
    
    special_status = {b.value for b in BlockResult}
    if status_result in special_status:
        #Propaga o status para que camadas superiores decidam como tratar a situação.
        logger.warning("special_status", status=status_result, url=normalized_url)
        return result
    
    message = result.get("detail") or result.get("message") or "Falha ao coletar dados do scraping"
    logger.error("scraping_failed", url=normalized_url, details=message)
    return {"status": "error", "detail": message}

def scrape_product_common(
        url: str,
        user_id: UUID,
        payload,
        product_type: Literal["monitored", "competitor"],
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Executa ``scrape_product_common_async`` em contexto síncrono """
    logger.info("start_scraping_sync", url=url, product_type=product_type)
    return asyncio.run(
        scrape_product_common_async(
            url=url,
            user_id=user_id,
            payload=payload,
            product_type=product_type,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            recovery_manager=recovery_manager
        )
    )
