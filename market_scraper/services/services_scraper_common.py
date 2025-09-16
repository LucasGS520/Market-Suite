""" Funções e utilidades compartilhadas entre os scrapers

Responsável apenas por obter e interpretar o HTML dos produtos.
Qualquer persistência de dados ou autenticação deve ser tratada
por camadas externas, como o módulo ``market_alert``. Também
realiza o pré-processamento dos dados, tratamento de status
especiais (bloqueios e ``NOT_MODIFIED``) e integração com cache.
"""

from __future__ import annotations

from typing import Literal, Any
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
from market_scraper.utils.mechanicalsoup_login import login_and_get_cookies

from shared.enums import BlockResult
from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping

from market_scraper.services.domain_policy import strategies_for, pipeline_steps_for, pipeline_execution_mode_for, strategy_execution_mode_for
from market_scraper.services.multi_strategy_orchestrator import MultiStrategyScraperOrchestrator
from market_scraper.services.synergic_pipeline import SynergicPipeline


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
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    recovery_manager: BlockRecoveryManager | None = None,
    mechanicalsoup_config: dict | None = None,
    **extra_kwargs,
) -> dict:
    """ Orquestra o fluxo de scraping com cache, pipeline e estratégias

    A rotina verifica o cache inteligente, executa o ``SynergicPipeline`` definido
    para o domínio/contexto e, quando necessário, aciona o orquestrador de
    estratégias. Cada etapa registra logs estruturados, persiste metadados
    seguros e renova TTL do cache quando um resultado existente é reutilizado.
    O compartilhamento de contexto garante que etapas subsequentes aproveitem
    cookies, HTML renderizado e outras dependências resolvidas previamente.
    """
    #Registra o início do fluxo de scraping
    logger.info("start_scraping", url=url, product_type=product_type)

    cookies = None
    if mechanicalsoup_config:
        logger.info("mechanicalsoup_login", url=mechanicalsoup_config.get("url"))
        try:
            cookies = await login_and_get_cookies(mechanicalsoup_config)
        except Exception as err:
            logger.warning("mechanicalsoup_login_failed", erro=str(err))
        else:
            extra_kwargs.setdefault("cookies", cookies)

    #Mantém a URL original, sem normalização para mobile
    normalized_url = url
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
            cache_manager.touch(marketplace=marketplace, url=normalized_url)
            logger.info("cache_used", url=normalized_url)
            return {"status": "success", "details": details}
    else:
        logger.info("cache_not_found", url=normalized_url)


    shared_context: dict[str, Any] = {"url": normalized_url, "product_type": product_type}
    if cookies:
        shared_context["cookies"] = cookies

    def _persist_success(details: dict[str, Any], *, extraction_method: str | None = None) -> None:
        """ Armazena dados válidos no cache inteligente com metadados """

        headers_cache = get_cache_headers(normalized_url)
        cache_value: dict[str, Any] = {"data": details}
        if headers_cache.get("etag") or headers_cache.get("last_modified"):
            cache_value["headers"] = headers_cache

        metadata: dict[str, Any] = {}
        if extraction_method:
            metadata["extraction_method"] = extraction_method

        safe_context_keys = {"content_signature", "selectorlib_template"}
        safe_context = {
            key: shared_context[key]
            for key in safe_context_keys
            if key in shared_context
        }
        if safe_context:
            metadata["context"] = safe_context

        if metadata:
            cache_value["metadata"] = metadata

        cache_manager.set(
            marketplace=marketplace,
            url=normalized_url,
            value=cache_value,
        )
        logger.info("stored_cache", url=normalized_url, metadata_keys=list(metadata.keys()))

    pipeline_context = "competitor" if product_type == "competitor" else "default"
    steps = pipeline_steps_for(normalized_url, context=pipeline_context)
    if steps:
        execution_mode = pipeline_execution_mode_for(normalized_url, context=pipeline_context)
        logger.info("running_pipeline", url=normalized_url, context=pipeline_context, execution_mode=execution_mode, steps=len(steps))
        pipeline = SynergicPipeline(steps=steps, execution_mode=execution_mode)
        pipeline_result = await pipeline.run(shared_context)
        shared_context.update(pipeline_result.get("shared_context", {}))

        for entry in pipeline_result.get("results", []):
            status_step = entry.get("status")
            if status_step == "success" and entry.get("details"):
                pipeline_details = entry["details"]
                try:
                    validator.validate(pipeline_details)
                except ValueError as err:
                    logger.info("pipeline_invalid_data", erro=str(err))
                    continue
                method = entry.get("extraction_method")
                _persist_success(pipeline_details, extraction_method=method)
                logger.info("pipeline_short_circuit", url=normalized_url, step=method)
                return {"status": "success", "details": pipeline_details}
            
            if status_step == "NOT_MODIFIED":
                cached_pipeline = cache_manager.get(marketplace=marketplace, url=normalized_url)
                if cached_pipeline:
                    cache_manager.touch(marketplace=marketplace, url=normalized_url)
                    logger.info("pipeline_not_modified", url=normalized_url)
                    return {"status": "NOT_MODIFIED", "details": cached_pipeline}

    orchestrator = MultiStrategyScraperOrchestrator(strategy_selector=strategies_for)
    logger.info("running_orchestrator", url=normalized_url)
    try:
        result = await orchestrator.scrape(
            url=normalized_url,
            user_id=user_id,
            payload=payload,
            product_type=product_type,
            execution_mode=strategy_execution_mode_for(normalized_url),
            shared_context=shared_context,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            recovery_manager=recovery_manager,
            **extra_kwargs,
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
 
        final_context = result.get("shared_context")
        if isinstance(final_context, dict):
            shared_context.update(final_context)

        _persist_success(details, extraction_method=result.get("extraction_method"))
        logger.info("scraping_success", url=normalized_url)
        return {"status": "success", "details": details}
    
    if status_result == "NOT_MODIFIED":
        #Quando o servidor indica que o recurso não mudou, não há necessidade de processar o resultado. Caso exista um valor cacheado ele é anexado ao retorno apenas para fins informativos.   
        logger.info("content_not_modified", url=normalized_url)
        cached = cache_manager.get(marketplace=marketplace, url=normalized_url)
        if cached:
            cache_manager.touch(marketplace=marketplace, url=normalized_url)
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
    recovery_manager: BlockRecoveryManager | None = None,
    mechanicalsoup_config: dict | None = None, 
    **extra_kwargs,
) -> dict:
    """ Executa ``scrape_product_common_async`` de maneira síncrono """
    logger.info("start_scraping_sync", url=url, product_type=product_type)
    return asyncio.run(
        scrape_product_common_async(
            url=url,
            user_id=user_id,
            payload=payload,
            product_type=product_type,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            recovery_manager=recovery_manager,
            mechanicalsoup_config=mechanicalsoup_config,
            **extra_kwargs,
        )
    )
