""" Ponto de entrada da aplicação FastAPI do serviço de scraping

O módulo cria a instância principal do FastAPI, registra as rotas
de saúde e scraping, e gerencia o ciclo de vida do PlaywrightPool
(Camada 3 de aquisição de HTML).
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

#Importação relativa para execução como pacote
from .routes import routes_health, routes_scraper
from .services.playwright_pool import playwright_pool


logger = structlog.get_logger("market_scraper.main")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """ Gerencia recursos de longa duração da aplicação."""
    # ── Startup ──────────────────────────────────────────────────────────
    try:
        await playwright_pool.startup()
    except Exception as exc:
        #Pool indisponível não impede o serviço de funcionar —
        #Camada PLaywright simplesmente retornará PlaywrightPoolNotReadyError.
        logger.warning("playwright_pool_startup_failed", error=str(exc))

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    await playwright_pool.shutdown()


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
#Disponibiliza o endpoint com dois prefixos por compatibilidade ("/scraper" e "/scrape")
app.include_router(routes_scraper.router, prefix="/scraper")

#A variável `app` é exposta para uso pelo Uvicorn
__all__ = ["app"]
