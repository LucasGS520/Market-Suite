""" Funções e utilidades compartilhadas entre os scrapers

Responsável apenas por obter e interpretar o HTML dos produtos.
Qualquer persistência de dados ou autenticação deve ser tratada
por camadas externas, como o módulo ``market_alert``.
"""

from __future__ import annotations

from typing import Dict, Optional, Literal, Callable, Any
from uuid import UUID
from datetime import datetime, timezone

import asyncio
import structlog

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder

from scraper_app.core.config import settings

from utils.circuit_breaker import CircuitBreaker
from utils.redis_client import get_redis_client, is_scraping_suspended, suspend_scraping
from utils.rate_limiter import RateLimiter
from utils.ml_url import canonicalize_ml_url, is_product_url

from scraper_app.utils.constants import to_mobile_url, THROTTLE_RATE, THROTTLE_CAPACITY, JITTER_RANGE, PRODUCT_HOSTS
from scraper_app.utils.user_agent_manager import IntelligentUserAgentManager
from scraper_app.utils.humanized_delay import HumanizedDelayManager
from scraper_app.utils.throttle_manager import ThrottleManager
from scraper_app.utils.http_utils import extract_hostname
from scraper_app.utils.block_detector import detect_block, BlockResult
from scraper_app.utils.block_recovery import BlockRecoveryManager
from scraper_app.utils.audit_logger import audit_scrape
from scraper_app.utils.price import parse_price_str
from scraper_app.utils.robots_txt import RobotsTxtParser
from scraper_app.utils.cookie_manager import cookie_manager
from scraper_app.utils.playwright_client import get_playwright_client
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import scraper_app.services.services_parser as parser
from scraper_app.services.services_parser import CaptchaDetectedError
from scraper_app.services.services_cache_scraper import use_cache_if_not_modified, update_cache
from scraper_app.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from alert_app.metrics import (
    SCRAPER_HTTP_BLOCKED_TOTAL,
    SCRAPER_CAPTCHA_TOTAL,
    SCRAPER_REQUESTS_TOTAL,
    SCRAPER_RESPONSE_SIZE_BYTES,
    SCRAPER_URL_STATUS_TOTAL
)


logger = structlog.get_logger("scraper_common")
#Conexão Redis usada para cache e controle
redis_client = get_redis_client()

#ClienteHTTP é criado dinamicamente por requisição

#Gerenciador de User-Agent com rotação inteligente
ua_manager = IntelligentUserAgentManager()

async def fetch_html_playwright(url: str) -> str:
    """ Retorna apenas o HTML da ``url`` utilizando Playwright

    A função cria um cliente Playwright e delega a ele a navegação e espera por
    elementos obrigatórios antes de capturar o conteúdo.
    """
    async with get_playwright_client() as client:
        html = await client.fetch_html(url)
        return html

async def _scrape_product_common(
        *,
        url: str,
        user_id: UUID,
        payload: MonitoredProductCreateScraping | CompetitorProductCreateScraping,
        product_type: Literal["monitored", "competitor"],
        persist_fn: Callable[[dict], Any] | None = None,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Executa o fluxo assíncrono de scraping usando Playwright

    Não realiza persistência nem autenticação. Caso seja necessário
    salvar os dados obtidos, forneça ``persist_fn`` para que o
    chamador trate dessa responsabilidade.
    """
    if product_type == "monitored":
        rate_limiter = rate_limiter or RateLimiter(
            redis_key="monitored",
            max_requests=settings.MONITORED_RATE_LIMIT,
            window_seconds=settings.RATE_LIMIT_WINDOW
        )
    else:
        rate_limiter = rate_limiter or RateLimiter(
            redis_key="competitor",
            max_requests=settings.COMPETITOR_SERVICE_RATE_LIMIT,
            window_seconds=settings.RATE_LIMIT_WINDOW
        )

    circuit_breaker = circuit_breaker or CircuitBreaker()
    recovery_manager = recovery_manager or BlockRecoveryManager(
        ua_manager=ua_manager,
        cookie_manager=cookie_manager
    )

    #Controla a taxa de requisições e aplica jitter entre elas
    throttle = ThrottleManager(
        rate=THROTTLE_RATE,
        capacity=THROTTLE_CAPACITY,
        jitter_range=JITTER_RANGE,
        circuit_breaker=circuit_breaker,
        rate_limiter=rate_limiter
    )
    #Simula atraso humano antes de cada requisição
    human_delay = HumanizedDelayManager()

    url_host = extract_hostname(url)

    if is_scraping_suspended():
        if product_type == "competitor":
            logger.warning("scraping_suspended", url=str(url), user_id=str(user_id))
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Scraping temporariamente suspenso via flag Redis para {url}"
        )

    circuit_key = f"user:{user_id}:{payload.product_url}"
    if not circuit_breaker.allow_request(circuit_key):
        logger.warning("circuit_blocked", url=str(url), user_id=str(user_id))
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Scraping suspenso temporariamente por falhas repetitivas {url}" if product_type == "competitor" else f"Scraping suspenso temporariamente por falhas repetitivas em {url}"
        )

    original_url = str(url)
    target_url = to_mobile_url(original_url)
    url_host = extract_hostname(target_url)

    #Respeita eventuais diretivas de robots.txt
    robots = RobotsTxtParser(original_url)
    delay = robots.get_crawl_delay(user_agent="*")
    if delay:
        throttle.jitter_min = delay * 0.5
        throttle.jitter_max = delay * 1.5

    human_delay.wait(None)
    throttle.wait(identifier="get", circuit_key=circuit_key)

    #HTML capturado da página. Se ocorrer bloqueio, pode ser substituído
    html: str | None = None
    try:
        html = await fetch_html_playwright(target_url)
        SCRAPER_REQUESTS_TOTAL.labels(method="GET", status_code=200).inc()
        SCRAPER_RESPONSE_SIZE_BYTES.labels(method="GET", status_code=200).observe(len(html))
        audit_scrape(stage="get", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error=None)
        human_delay.wait(html)
    except PlaywrightTimeoutError as e:
        logger.warning("playwright_timeout", url=target_url, error=str(e))
        circuit_breaker.record_failure(circuit_key)
        SCRAPER_HTTP_BLOCKED_TOTAL.inc()
        recovered = await recovery_manager.handle_block("timeout", url=target_url)
        if recovered is None:
            audit_scrape(stage="error", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error=str(e))
            SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Erro ao obter HTML" if product_type == "monitored" else "Erro ao obter HTML concorrente"
            )

        html = recovered
        SCRAPER_REQUESTS_TOTAL.labels(method="GET", status_code=200).inc()
        human_delay.wait(html)
        audit_scrape(stage="block_recovered", url=target_url, payload=jsonable_encoder(payload), html=None, details=None, error=None)
    except Exception as e:
        logger.error("get_request_failed", url=target_url, error=str(e))
        circuit_breaker.record_failure(circuit_key)
        #Tenta classificar o tipo de bloqueio a partir da mensagem da exceção
        block_type = "429"
        msg = str(e).lower()
        if "403" in msg:
            block_type = "403"
        elif "429" in msg:
            block_type = "429"

        SCRAPER_HTTP_BLOCKED_TOTAL.inc()
        #Aciona o gerenciador de recuperação informando o tipo de bloqueio
        recovered = await recovery_manager.handle_block(block_type, url=target_url)
        if recovered is None:
            #Falha definitiva registra e interrompe o fluxo
            audit_scrape(stage="error", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error=str(e))
            SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Erro ao obter HTML" if product_type == "monitored" else "Erro ao obter HTML concorrente"
            )

        #Se houver HTML recuperado, continua o fluxo normalmente
        html = recovered
        SCRAPER_REQUESTS_TOTAL.labels(method="GET", status_code=200).inc()
        human_delay.wait(html)
        audit_scrape(stage="block_recovered", url=target_url, payload=jsonable_encoder(payload), html=None, details=None, error=None)

    if product_type == "monitored":
        cached_result = use_cache_if_not_modified(
            target_url=target_url,
            html=html,
            payload=payload,
            persist_fn=persist_fn,
            circuit_breaker=circuit_breaker,
            circuit_key=circuit_key,
            id_key="product_id",
            endpoint="monitored_scrape",
        )
    else:
        cached_result = use_cache_if_not_modified(
            target_url=target_url,
            html=html,
            payload=payload,
            persist_fn=persist_fn,
            circuit_breaker=circuit_breaker,
            circuit_key=circuit_key,
            id_key="competitor_id",
            endpoint="competitor_scrape",
        )

    if cached_result:
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="success").inc()
        return cached_result

    if not parser.looks_like_product_page(html):
        logger.warning("not_product_page", url=original_url)
        audit_scrape(stage="error", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error="not_product_page")
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Página não é de produto")

    try:
        details: Dict[str, Optional[str]] = parser.parse_product_details(html, target_url)
        logger.debug("parsed_details", details=details)
        logger.debug("raw_price_extracted", url=original_url, raw_price=details.get("current_price"))
        audit_scrape(stage="parser", url=target_url, payload=payload.model_dump(), html=None, details=details, error=None)
    except CaptchaDetectedError as exc:
        logger.warning("captcha_detected", url=original_url)
        circuit_breaker.record_failure(circuit_key)
        SCRAPER_CAPTCHA_TOTAL.inc()
        audit_scrape(stage="error", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error=str(exc))
        #Tenta recuperar o HTML caso o site apresente CAPTCHA
        recovered = await recovery_manager.handle_block("captcha", url=target_url)
        if recovered:
            html = recovered
            audit_scrape(stage="captcha_recovered", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error=None)
            try:
                details = parser.parse_product_details(html, target_url)
                logger.debug("parsed_details", details=details)
                logger.debug("raw_price_extracted", url=original_url, raw_price=details.get("current_price"))
                audit_scrape(stage="parser", url=target_url, payload=payload.model_dump(), html=None, details=details, error=None)
            except Exception as exc2:
                logger.error("parser_failed", url=original_url, error=str(exc2))
                circuit_breaker.record_failure(circuit_key)
                audit_scrape(stage="error", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error=str(exc2))
                SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=("Erro ao extrair dados do produto" if product_type == "monitored" else f"Erro ao extrair dados do produto concorrente: {exc2}")
                )
        else:
            SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
            return {"status": "captcha"}
    except ValueError as exc:
        logger.error("invalid_product_data", url=original_url, error=str(exc))
        circuit_breaker.record_failure(circuit_key)
        audit_scrape(stage="error", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error=str(exc))
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception as exc:
        logger.error("parser_failed", url=original_url, erro=str(exc))
        circuit_breaker.record_failure(circuit_key)
        audit_scrape(stage="error", url=target_url, payload=jsonable_encoder(payload), html=html, details=None, error=str(exc))
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=("Erro ao extrair dados do produto" if product_type == "monitored" else f"Erro ao extrair dados do produto concorrente: {exc}")
        )

    raw_current = details.get("current_price")
    if raw_current is None:
        circuit_breaker.record_failure(circuit_key)
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("Preço não encontrado no HTML" if product_type == "monitored" else "Preço não encontrado no HTML concorrente")
        )

    current_price = parse_price_str(raw_current, target_url)

    if persist_fn:
        new_id = persist_fn(details)
    else:
        new_id = None

    update_cache(target_url, details, html, None)
    audit_scrape(
        stage="persist",
        url=target_url,
        payload=jsonable_encoder(payload),
        html=None,
        details=details,
        error=None,
    )
    circuit_breaker.record_success(circuit_key)
    SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="success").inc()
    if new_id is not None:
        key = "product_id" if product_type == "monitored" else "competitor_id"
        return {"status": "success", key: str(new_id)}
    return {"status": "success", "details": details}


def scrape_product_common(
        url: str,
        user_id: UUID,
        payload,
        product_type: Literal["monitored", "competitor"],
        persist_fn: Callable[[dict], Any] | None = None,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Executa ``_scrape_product_common`` em contexto síncrono """
    return asyncio.run(
        _scrape_product_common(
            url=url,
            user_id=user_id,
            payload=payload,
            product_type=product_type,
            persist_fn=persist_fn,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            recovery_manager=recovery_manager
        )
    )
