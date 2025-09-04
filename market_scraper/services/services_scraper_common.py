""" Funções e utilidades compartilhadas entre os scrapers

Responsável apenas por obter e interpretar o HTML dos produtos.
Qualquer persistência de dados ou autenticação deve ser tratada
por camadas externas, como o módulo ``market_alert``.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import asyncio
from urllib.parse import urlparse

from fastapi import HTTPException, status

from market_scraper.utils.constants import to_mobile_url
from market_scraper.utils.http_utils import extract_hostname
from market_scraper.utils.intelligent_cache import IntelligentCacheManager
from market_scraper.utils.rate_limiter import RateLimiter
from market_scraper.utils.circuit_breaker import CircuitBreaker
from market_scraper.utils.block_recovery import BlockRecoveryManager
from market_scraper.utils.robots_txt import RobotsTxtParser
from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager

from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping

from market_scraper.services.domain_policy import strategies_for
from market_scraper.services.multi_strategy_orchestrator import MultiStrategyScraperOrchestrator


#Gerenciador de cache inteligente para produtos
cache_manager = IntelligentCacheManager()
#Gerenciador de user-agent para consultas ao robots.txt
ua_manager = IntelligentUserAgentManager()

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
    consultar o cache e disparar as estratégias. A função delega a lógica
    de seleção e execução para o :class:`MultiStrategyScraperOrchestrator`,
    que também valida os dados obtidos e registra métricas de fallback entre estratégias
    """
    #Converte a URL para formato canônico (mobile) para evitar variações
    normalized_url = to_mobile_url(url)
    marketplace = extract_hostname(normalized_url)

    #Verifica diretivas de robots.txt antes de prosseguir
    parser = RobotsTxtParser(base_url=normalized_url)
    user_agent = ua_manager.get_user_agent("scraper_common")
    path = urlparse(normalized_url).path or "/"
    #Aborta com HTTP 403 quando o caminho não é permitido
    if not await parser.is_allowed(path, user_agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bloqueado pelo robots.txt",
        )
    #Respeita o crawl-delay recomendado pelo site
    delay = await parser.get_crawl_delay(user_agent)
    if delay:
        await asyncio.sleep(delay)

    #Verifica se já existe conteúdo cacheado para a URL normalizada e o marketplace
    cached = cache_manager.get(marketplace=marketplace, url=normalized_url)
    if cached:
        return {"status": "success", "details": cached}

    orchestrator = MultiStrategyScraperOrchestrator(strategy_selector=strategies_for)
    result = await orchestrator.scrape(
        url=normalized_url,
        user_id=user_id,
        payload=payload,
        product_type=product_type,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        recovery_manager=recovery_manager,
    )

    #Armazena no cache caso o scraping tenha sido bem-sucedido
    if result.get("status") == "success" and result.get("details"):
        cache_manager.set(marketplace=marketplace, url=normalized_url, value=result["details"])

    return result

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
