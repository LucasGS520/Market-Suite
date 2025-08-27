""" Funções e utilidades compartilhadas entre os scrapers

Responsável apenas por obter e interpretar o HTML dos produtos.
Qualquer persistência de dados ou autenticação deve ser tratada
por camadas externas, como o módulo ``market_alert``.
"""

from __future__ import annotations

from typing import Dict, Optional, Literal
from uuid import UUID

import asyncio
import structlog
from urllib.parse import urlparse

from fastapi import HTTPException, status

from market_scraper.core.config_scraper import settings

from shared.utils.redis_client import is_scraping_suspended
from shared.enums import BlockResult
from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from shared.metrics.metrics_scraper import (
    SCRAPER_HTTP_BLOCKED_TOTAL,
    SCRAPER_CAPTCHA_TOTAL,
    SCRAPER_REQUESTS_TOTAL,
    SCRAPER_RESPONSE_SIZE_BYTES,
    SCRAPER_URL_STATUS_TOTAL,
)

from market_scraper.utils.circuit_breaker import CircuitBreaker
from market_scraper.utils.rate_limiter import RateLimiter
from market_scraper.utils.constants import to_mobile_url, THROTTLE_RATE, THROTTLE_CAPACITY, JITTER_RANGE
from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager
from market_scraper.utils.humanized_delay import HumanizedDelayManager
from market_scraper.utils.throttle_manager import ThrottleManager
from market_scraper.utils.http_utils import extract_hostname, parse_retry_after
from market_scraper.utils.block_recovery import BlockRecoveryManager
from market_scraper.utils.price import parse_price_str
from market_scraper.utils.robots_txt import RobotsTxtParser
from market_scraper.utils.cookie_manager import cookie_manager
from market_scraper.utils.playwright_client import get_playwright_client
from market_scraper.utils.intelligent_cache import IntelligentCacheManager
from market_scraper.utils.http_cache import get_cache_headers, store_cache_headers, ContentSignature, NOT_MODIFIED

import httpx

from market_scraper.services.domain_policy import strategies_for

import market_scraper.services.services_parser as parser
from market_scraper.services.services_parser import CaptchaDetectedError
from market_scraper.services.services_cache_scraper import get_cached_html, set_cached_html
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


logger = structlog.get_logger("scraper_common")

#ClienteHTTP é criado dinamicamente por requisição

#Gerenciador de User-Agent com rotação inteligente
ua_manager = IntelligentUserAgentManager()
#Gerenciador de cache inteligente para produtos
cache_manager = IntelligentCacheManager()

#Contador de tentativas consecutivas para respostas HTTP 429 por chave de circuito
_HTTP_429_ATTEMPTS: dict[str, int] = {}

async def fetch_html_playwright(url: str) -> str:
    """ Retorna apenas o HTML da ``url`` utilizando Playwright

    A função cria um cliente Playwright e delega a ele a navegação e espera por
    elementos obrigatórios antes de capturar o conteúdo.
    """
    async with get_playwright_client() as client:
        try:
            html = await client.fetch_html(url)
            return html
        except HTTPException as exc:
            #Quando o Playwright retorna ``429``, respeita o tempo sugerido pelo servidor
            if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                wait_for = parse_retry_after((exc.headers or {}).get("Retry-After"))
                if wait_for:
                    delay = HumanizedDelayManager()
                    await delay.wait_async(None, reflection_time=wait_for)
            raise

async def _recover_html(
    block_type: BlockResult,
    *,
    url: str,
    url_host: str,
    recovery_manager: BlockRecoveryManager,
    human_delay: HumanizedDelayManager,
    product_type: Literal["monitored", "competitor"],
) -> str:
    """ Tenta recuperar o HTML após um bloqueio do site """
    recovered = await recovery_manager.handle_block(block_type, url=url)
    if recovered is None:
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Erro ao obter HTML" if product_type == "monitored" else "Erro ao obter HTML concorrente",
        )

    SCRAPER_REQUESTS_TOTAL.labels(method="GET", status_code=200).inc()
    #Aguarda de maneira assíncrona antes de continuar o fluxo
    await human_delay.wait_async(recovered)
    return recovered

async def _get_html(
    *,
    target_url: str,
    circuit_key: str,
    product_type: Literal["monitored", "competitor"],
    url_host: str,
    throttle: ThrottleManager,
    human_delay: HumanizedDelayManager,
    circuit_breaker: CircuitBreaker,
    recovery_manager: BlockRecoveryManager,
):
    """ Obtém o HTML da página utilizando cache e recuperação de bloqueios

    Antes de realizar a navegação completa, executa uma requisição ``HEAD``
    condicional com os valores ``ETag`` e ``Last-Modified`` em cache,
    garantindo que apenas strings válidas sejam enviadas. A requisição ``HEAD``
    deve imitar a navegação real adicionando ``User-Agent`` e cookies atuais,
    reduzindo a chance de bloqueios pelo servidor. Caso o servidor responda
    ``304 Not Modified``, o fluxo é encerrado retornando a sentinela ``NOT_MODIFIED``
    """
    #Aguarda para simular leitura humana e respeitar a taxa de requisições
    await human_delay.wait_async(None)
    await throttle.wait_async(identifier="get", circuit_key=circuit_key)

    #Recupera cabeçalhos previamente armazenados para uso condicional
    cached_headers = get_cache_headers(target_url)
    conditional_headers: dict[str, str] = {}

    #Garante que apenas valores de texto sejam enviados como cabeçalhos
    etag = cached_headers.get("etag")
    if isinstance(etag, str):
        conditional_headers["If-None-Match"] = etag

    last_modified = cached_headers.get("last_modified")
    if isinstance(last_modified, str):
        #Reutiliza o valor do cabeçalho HTTP "Last-Modified" salvo anteriormente
        conditional_headers["If-Modified-Since"] = last_modified

    #Adiciona cabeçalhos de navegação real (incluindo User-Agent) para evitar bloqueios
    ua = ua_manager.get_user_agent(circuit_key)
    request_headers = {**conditional_headers, "User-Agent": ua}
    cookies = cookie_manager.get_cookies(circuit_key)

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            #Utiliza ``request_headers`` para enviar User-Agent e cabeçalhos condicionais
            head_response = await client.head(
                target_url, headers=request_headers, cookies=cookies
            )
    except Exception as err:
        logger.warning("head_request_failed", url=target_url, error=str(err))
        head_response = None
    else:
        try:
            cookie_manager.update_from_response(circuit_key, head_response)
        except Exception:
            logger.debug("cookie_update_failed", url=target_url)

    if head_response is not None:
        SCRAPER_REQUESTS_TOTAL.labels(method="HEAD", status_code=head_response.status_code).inc()
        if head_response.status_code == 304:
            SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="not_modified").inc()
            return NOT_MODIFIED
        if head_response.status_code == 429:
            retry_after = parse_retry_after(head_response.headers.get("Retry-After"))
            if retry_after:
                #Suspende novas tentativas conforme indicação do servidor
                await human_delay.wait_async(None, reflection_time=retry_after)
            circuit_breaker.record_failure(circuit_key)
            SCRAPER_HTTP_BLOCKED_TOTAL.inc()
            return await _recover_html(
                BlockResult.HTTP_429,
                url=target_url,
                url_host=url_host,
                recovery_manager=recovery_manager,
                human_delay=human_delay,
                product_type=product_type,
            )
        store_cache_headers(
            target_url,
            etag=head_response.headers.get("etag"),
            #Utiliza a grafia padrão do cabeçalho HTTP ``Last-Modified``
            last_modified=head_response.headers.get("Last-Modified"),
        )

    html: str | None = await get_cached_html(target_url)
    if html is None:
        try:
            html = await fetch_html_playwright(target_url)
            SCRAPER_REQUESTS_TOTAL.labels(method="GET", status_code=200).inc()
            SCRAPER_RESPONSE_SIZE_BYTES.labels(method="GET", status_code=200).observe(len(html))
            await set_cached_html(target_url, html)
            await human_delay.wait_async(html)
        except PlaywrightTimeoutError as e:
            logger.warning("playwright_timeout", url=target_url, error=str(e))
            circuit_breaker.record_failure(circuit_key)
            SCRAPER_HTTP_BLOCKED_TOTAL.inc()
            html = await _recover_html(
                BlockResult.UNKNOWN,
                url=target_url,
                url_host=url_host,
                recovery_manager=recovery_manager,
                human_delay=human_delay,
                product_type=product_type,
            )
        except HTTPException as e:
            #Erros HTTP explícitos retornados pelo Playwright
            logger.error("get_request_failed", url=target_url, error=str(e))
            circuit_breaker.record_failure(circuit_key)
            retry_after = parse_retry_after((e.headers or {}).get("Retry-After"))
            if e.status_code == status.HTTP_403_FORBIDDEN:
                block_type = BlockResult.HTTP_403
            elif e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                block_type = BlockResult.HTTP_429
                if retry_after:
                    #Aguarda o tempo solicitado pelo servidor antes de prosseguir
                    await human_delay.wait_async(None, reflection_time=retry_after)
            else:
                block_type = BlockResult.UNKNOWN
            SCRAPER_HTTP_BLOCKED_TOTAL.inc()
            html = await _recover_html(
                block_type,
                url=target_url,
                url_host=url_host,
                recovery_manager=recovery_manager,
                human_delay=human_delay,
                product_type=product_type,
            )
        except Exception as e:
            logger.error("get_request_failed", url=target_url, error=str(e))
            circuit_breaker.record_failure(circuit_key)
            msg = str(e).lower()
            if "403" in msg:
                block_type = BlockResult.HTTP_403
            elif "429" in msg:
                block_type = BlockResult.HTTP_429
            else:
                block_type = BlockResult.UNKNOWN

            SCRAPER_HTTP_BLOCKED_TOTAL.inc()
            if block_type == BlockResult.HTTP_429:
                #Incrementa o número de tentativas consecutivas e aplica backoff
                attempt = _HTTP_429_ATTEMPTS.get(circuit_key, 0) + 1
                _HTTP_429_ATTEMPTS[circuit_key] = attempt
                await throttle.backoff_async(attempt, circuit_key)
            else:
                #Qualquer outro bloqueio reinicia o contador de tentativas
                _HTTP_429_ATTEMPTS.pop(circuit_key, None)

            html = await _recover_html(
                block_type,
                url=target_url,
                url_host=url_host,
                recovery_manager=recovery_manager,
                human_delay=human_delay,
                product_type=product_type,
            )
    else:
        SCRAPER_REQUESTS_TOTAL.labels(method="CACHE", status_code=200).inc()
        SCRAPER_RESPONSE_SIZE_BYTES.labels(method="CACHE", status_code=200).observe(len(html))
        await human_delay.wait_async(html)

    if html is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao obter HTML")

    #Reseta contador de 429 após obter o conteúdo com sucesso
    _HTTP_429_ATTEMPTS.pop(circuit_key, None)

    #Verifica se o conteúdo foi alterado desde a últma coleta
    signer = ContentSignature(target_url)
    if signer.check_or_update(html) is NOT_MODIFIED:
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="not_modified").inc()
        return NOT_MODIFIED

    return html

async def _parse_html(
    html: str,
    *,
    original_url: str,
    target_url: str,
    product_type: Literal["monitored", "competitor"],
    url_host: str,
    circuit_breaker: CircuitBreaker,
    circuit_key: str,
    recovery_manager: BlockRecoveryManager,
) -> dict:
    """ Interpreta o HTML e extrai os dados principais do produto """
    if not parser.looks_like_product_page(html):
        logger.warning("not_product_page", url=original_url)
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Página não é de produto")

    try:
        details: Dict[str, Optional[str]] = parser.parse_product_details(html, target_url)
        logger.debug("parsed_details", details=details)
        logger.debug("raw_price_extracted", url=original_url, raw_price=details.get("current_price"))
    except CaptchaDetectedError:
        logger.warning("captcha_detected", url=original_url)
        circuit_breaker.record_failure(circuit_key)
        SCRAPER_CAPTCHA_TOTAL.inc()
        #Tenta recuperar o HTML caso o site apresente CAPTCHA
        recovered = await recovery_manager.handle_block(BlockResult.CAPTCHA, url=target_url)
        if recovered:
            html = recovered
            try:
                details = parser.parse_product_details(html, target_url)
                logger.debug("parsed_details", details=details)
                logger.debug("raw_price_extracted", url=original_url, raw_price=details.get("current_price"))
            except Exception as exc2:
                logger.error("parser_failed", url=original_url, error=str(exc2))
                circuit_breaker.record_failure(circuit_key)
                SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=("Erro ao extrair dados do produto" if product_type == "monitored" else f"Erro ao extrair dados do produto concorrente: {exc2}"),
                )
        else:
            SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
            return {"status": BlockResult.CAPTCHA.value}
    except ValueError as exc:
        logger.error("invalid_product_data", url=original_url, error=str(exc))
        circuit_breaker.record_failure(circuit_key)
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception as exc:
        logger.error("parser_failed", url=original_url, erro=str(exc))
        circuit_breaker.record_failure(circuit_key)
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=("Erro ao extrair dados do produto" if product_type == "monitored" else f"Erro ao extrair dados do produto concorrente: {exc}"),
        )

    raw_current = details.get("current_price")
    if raw_current is None:
        circuit_breaker.record_failure(circuit_key)
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("Preço não encontrado no HTML" if product_type == "monitored" else "Preço não encontrado no HTML concorrente"),
        )

    #Garante que o preço extraído é valido
    parse_price_str(raw_current, target_url)

    circuit_breaker.record_success(circuit_key)
    SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="success").inc()
    return {"status": "success", "details": details}

async def scrape_playwright_async(
    *,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping | CompetitorProductCreateScraping,
    product_type: Literal["monitored", "competitor"],
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Executa o fluxo assíncrono de scraping usando Playwright """
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
        cookie_manager=cookie_manager,
    )

    #Controla a taxa de requisições e aplica jitter entre elas
    throttle = ThrottleManager(
        rate=THROTTLE_RATE,
        capacity=THROTTLE_CAPACITY,
        jitter_range=JITTER_RANGE,
        circuit_breaker=circuit_breaker,
        rate_limiter=rate_limiter,
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
            detail=f"Scraping suspenso temporariamente por falhas repetitivas {url}" if product_type == "competitor" else f"Scraping suspenso temporariamente por falhas repetitivas em {url}"
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
    delay = await robots.get_crawl_delay(user_agent="*")
    if delay:
        throttle.jitter_min = delay * 0.5
        throttle.jitter_max = delay * 1.5

    caminho = urlparse(target_url).path or "/"
    permitido = await robots.is_allowed(path=caminho, user_agent="*")
    if not permitido:
        logger.warning("robots_disallow", url=target_url)
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=url_host, status="failure").inc()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso proibido pelo robots.txt")

    html = await _get_html(
        target_url=target_url,
        circuit_key=circuit_key,
        product_type=product_type,
        url_host=url_host,
        throttle=throttle,
        human_delay=human_delay,
        circuit_breaker=circuit_breaker,
        recovery_manager=recovery_manager,
    )

    if html is NOT_MODIFIED:
        return {"status": "NOT_MODIFIED"}

    return await _parse_html(
        html,
        original_url=original_url,
        target_url=target_url,
        product_type=product_type,
        url_host=url_host,
        circuit_breaker=circuit_breaker,
        circuit_key=circuit_key,
        recovery_manager=recovery_manager,
    )

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

    As estratégias são avaliadas em sequência até que uma delas consiga
    extrair os dados do produto ou informe que o conteúdo analisado não
    foi modificado desde a última coleta. Quando ocorre qualquer um
    desses cenários, as demais estratégias não são executadas, evitando
    processamento desnecessário.
    """
    marketplace = extract_hostname(url)
    #Verifica se já existe conteúdo cacheado para esta URL e marketplace
    cached = cache_manager.get(marketplace=marketplace, url=url)
    if cached:
        return {"status": "success", "details": cached}

    strategies = strategies_for(url)
    if not strategies:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL não suportada")

    result = {"status": "error"}
    for strategy in strategies:
        if not strategy.supports_url(url):
            continue
        try:
            result = await strategy.get_data(
                url=url,
                headers=None,
                user_id=user_id,
                payload=payload,
                product_type=product_type,
                rate_limiter=rate_limiter,
                circuit_breaker=circuit_breaker,
                recovery_manager=recovery_manager,
            )
        except Exception:
            #Qualquer falha na estratégia atual gera status de erro e permite que o laço continue para tentar a próxima opção disponível
            result = {"status": "error"}
        #Encerra o loop em caso de sucesso ou quando nenhuma atualização é detecada (``NOT_MODIFIED``)
        if result.get("status") in ("success", "NOT_MODIFIED"):
            break

    #Armazena no cache caso o scraping tenha sido bem-sucedido
    if result.get("status") == "success" and result.get("details"):
        cache_manager.set(marketplace=marketplace, url=url, value=result["details"])

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
