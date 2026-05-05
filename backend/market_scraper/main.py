""" Ponto de entrada da aplicação FastAPI do serviço de scraping.

Cria a instância do FastAPI, registra rotas de saúde e scraping,
e gerencia o lifecycle do CrawleeRuntime (HTTP + browser fallback).
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .routes import routes_health, routes_scraper
from .collection import crawlee_runtime
from .core.config_scraper import settings as scraper_settings


logger = structlog.get_logger("market_scraper.main")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """ Gerencia recursos de longa duração da aplicação."""
    # ── Startup ──────────────────────────────────────────────────────────
    await crawlee_runtime.startup()

    proxy_available = bool(scraper_settings.SCRAPER_PROXY_URLS.strip())
    sensitive_domains_blocked = (
        scraper_settings.SCRAPER_ENV in {"staging", "production"} and not proxy_available
    )
    logger.info(
        "service_capability",
        env=scraper_settings.SCRAPER_ENV,
        proxy_available=proxy_available,
        sensitive_domains_supported=not sensitive_domains_blocked,
        browser_ready=crawlee_runtime.browser_ready,
        robots_mode=scraper_settings.SCRAPER_ROBOTS_MODE,
        rate_limiter_block_enabled=scraper_settings.SCRAPER_RATE_LIMITER_BLOCK_ENABLED,
        browser_concurrency=scraper_settings.SCRAPER_BROWSER_CONCURRENCY,
        http_budget_s=scraper_settings.SCRAPER_HTTP_BUDGET_SECONDS,
        browser_budget_s=scraper_settings.SCRAPER_BROWSER_BUDGET_SECONDS,
    )
    if sensitive_domains_blocked:
        logger.warning(
            "proxy_config_incomplete",
            env=scraper_settings.SCRAPER_ENV,
            message="SCRAPER_PROXY_URLS vazio; coleta de domínios sensíveis (ex.: Mercado Livre) será bloqueada",
        )

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    await crawlee_runtime.shutdown()


#Instância principal do aplicativo FastAPI
app = FastAPI(title="MarketScraper", lifespan=_lifespan)

#Manipulador para erros de validação da requisição
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """ Retorna mensagem amigável quando a URL é inválida """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "URL inválida ou malformada"},
    )

#Registro das rotas de saúde e de scraping
app.include_router(routes_health.router)
#Endpoint público único: POST /scraper/parse
app.include_router(routes_scraper.router, prefix="/scraper")

#A variável `app` é exposta para uso pelo Uvicorn
__all__ = ["app"]
