""" Funções e utilidades compartilhadas entre os scrapers

Este módulo centraliza toda a lógica de scraping utilizada tanto
para produtos monitorados quanto para produtos concorrentes.
Foi extraído para evitar repetição de código
"""

from __future__ import annotations

from typing import Dict, Optional, Literal
from uuid import UUID
from datetime import datetime, timezone

import asyncio
import structlog

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder

from app.core.config import settings

from app.utils.constants import to_mobile_url, THROTTLE_RATE, THROTTLE_CAPACITY, JITTER_RANGE, PRODUCT_HOSTS
from app.utils.user_agent_manager import IntelligentUserAgentManager
from app.utils.humanized_delay import HumanizedDelayManager
from app.utils.throttle_manager import ThrottleManager
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.redis_client import get_redis_client, is_scraping_suspended, suspend_scraping
from app.utils.http_utils import extract_hostname
from app.utils.block_detector import detect_block, BlockResult
from app.utils.block_recovery import BlockRecoveryManager
from app.utils.audit_logger import audit_scrape
from app.utils.price import parse_price_str, parse_optional_price_str
from app.utils.rate_limiter import RateLimiter
from app.utils.robots_txt import RobotsTxtParser
from app.utils.ml_url import canonicalize_ml_url, is_product_url
from app.utils.cookie_manager import cookie_manager
from app.utils.playwright_client import get_playwright_client
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import app.services.services_parser as parser
from app.services.services_parser import CaptchaDetectedError
from app.services.services_cache_scraper import use_cache_if_not_modified, update_cache
from app.crud.crud_monitored import create_or_update_monitored_product_scraped
from app.crud.crud_competitor import create_or_update_competitor_product_scraped
from app.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo, CompetitorProductCreateScraping, CompetitorScrapedInfo
from app.enums.enums_error_codes import ScrapingErrorType
from app.models.models_scraping_errors import ScrapingError
from app.tasks.compare_prices_tasks import compare_prices_task
from app.metrics import (
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
        db: Session,
        url: str,
        user_id: UUID,
        payload: MonitoredProductCreateScraping | CompetitorProductCreateScraping,
        product_type: Literal["monitored", "competitor"],
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Executa o fluxo assíncrono de scraping usando Playwright

    Aplica limites de taxa e atrasos humanizados nas requisições,
    obtém o HTML da página (se houver falha, tenta recuperar com BlockRecoveryManager)
    e realiza parsing, persistência e atualização de cache
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
            db=db,
            target_url=target_url,
            html=html,
            payload=payload,
            persist_fn=lambda cached: (
                lambda prod: (compare_prices_task.delay(str(prod.id)), prod)[1]
            )(
                create_or_update_monitored_product_scraped(
                    db=db,
                    user_id=user_id,
                    product_data=payload,
                    scraped_info=MonitoredScrapedInfo(
                        current_price=parse_price_str(cached.get("current_price"), target_url),
                        thumbnail=cached.get("thumbnail"),
                        free_shipping=(cached.get("shipping") == "Frete Grátis")
                    ),
                    last_checked=datetime.now(timezone.utc)
                )
            ),
            circuit_breaker=circuit_breaker,
            circuit_key=circuit_key,
            id_key="product_id",
            endpoint="monitored_scrape"
        )
    else:
        cached_result = use_cache_if_not_modified(
            db=db,
            target_url=target_url,
            html=html,
            payload=payload,
            persist_fn=lambda cached: create_or_update_competitor_product_scraped(
                db=db,
                product_data=payload,
                scraped_info=CompetitorScrapedInfo(
                    name=cached.get("name", ""),
                    current_price=parse_price_str(cached.get("current_price"), target_url),
                    old_price=parse_optional_price_str(cached.get("old_price"), target_url),
                    thumbnail=cached.get("thumbnail"),
                    free_shipping=(cached.get("shipping") == "Frete Grátis"),
                    seller=cached.get("seller"),
                    seller_rating=None
                ),
                last_checked=datetime.now(timezone.utc)
            ),
            circuit_breaker=circuit_breaker,
            circuit_key=circuit_key,
            id_key="competitor_id",
            endpoint="competitor_scrape"
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

    if product_type == "monitored":
        try:
            product_id = create_or_update_monitored_product_scraped(
                db=db,
                user_id=user_id,
                product_data=payload,
                scraped_info=MonitoredScrapedInfo(
                    current_price=current_price,
                    thumbnail=details.get("thumbnail"),
                    free_shipping=(details.get("shipping") == "Frete Grátis")
                ),
                last_checked=datetime.now(timezone.utc)
            )
            compare_prices_task.delay(str(product_id.id))
            update_cache(target_url, details, html, None)
        except Exception as exc:
            logger.error("persist_failed", error=str(exc))
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao salvar produto")
        audit_scrape(
            stage="persist",
            url=target_url,
            payload=jsonable_encoder(payload),
            html=None,
            details={"product_id": str(product_id.id), "current_price": str(current_price)},
            error=None
        )
        logger.info("monitored_product_saved", product_id=str(product_id.id))
        circuit_breaker.record_success(circuit_key)
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="success").inc()
        return {"status": "success", "product_id": str(product_id.id)}
    else:
        old_price = parse_optional_price_str(details.get("old_price"), original_url)
        competitor_id = create_or_update_competitor_product_scraped(
            db=db,
            product_data=payload,
            scraped_info=CompetitorScrapedInfo(
                name=details.get("name", ""),
                current_price=current_price,
                old_price=old_price,
                thumbnail=details.get("thumbnail"),
                free_shipping=(details.get("shipping") == "Frete Grátis"),
                seller=details.get("seller"),
                seller_rating=None
            ),
            last_checked=datetime.now(timezone.utc)
        )
        update_cache(target_url, details, html, None)
        audit_scrape(
            stage="persist",
            url=target_url,
            payload=jsonable_encoder(payload),
            html=None,
            details={"competitor_id": str(competitor_id.id), "current_price": str(current_price)},
            error=None
        )
        logger.info("competitor_product_saved", competitor_id=str(competitor_id))
        circuit_breaker.record_success(circuit_key)
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="success").inc()
        return {"status": "success", "competitor_id": str(competitor_id)}


def scrape_product_common(
        db: Session,
        url: str,
        user_id: UUID,
        payload,
        product_type: Literal["monitored", "competitor"],
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Executa ``_scrape_product_common`` em contexto síncrono """
    return asyncio.run(
        _scrape_product_common(
            db=db,
            url=url,
            user_id=user_id,
            payload=payload,
            product_type=product_type,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            recovery_manager=recovery_manager
        )
    )
