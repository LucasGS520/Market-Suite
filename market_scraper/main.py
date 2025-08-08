""" Aplicação principal do serviço de scraping via FastAPI """

import logging
import time

import structlog

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

import scraper_app.metrics as metrics_module
from scraper_app.core.config import settings

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
except Exception:
    FastAPIInstrumentor = None
    LoggingInstrumentor = None

#Configuração de Logs
def configure_logging() -> None:
    """ Configura o structlog para saida JSON estruturada """
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[structlog.processors.TimeStamper(fmt="iso")],
        )
    )

    class MetricsLogHandler(logging.Handler):
        """ Handler que incrementa métricas por volume de logs """

        def emit(self, record: logging.LogRecord) -> None:
            level = record.levelname.lower()
            try:
                metrics_module.LOG_ENTRIES_TOTAL.labels(level=level).inc()
            except Exception:
                pass

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addHandler(MetricsLogHandler())
    root.setLevel(logging.INFO)


#Executa a configuração de Logging antes de criar a aplicação
configure_logging()
logger = structlog.get_logger("marketscraper")

#Limitador de taxa baseado no endereço IP da requisição
limiter = Limiter(key_func=get_remote_address)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """ Retorna mensagem de erro amigável quando o limite é excedido """
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas requisições. Tente novamente mais tarde."},
    )

class MetricsMiddleware(BaseHTTPMiddleware):
    """ Middleware para coletar métricas de requisições HTTP """

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        latency = time.time() - start

        #Contabiliza a requisição
        metrics_module.HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
        ).inc()

        #Registra erros quando ocorrerem
        if response.status_code >= 400:
            try:
                metrics_module.API_ERRORS_TOTAL.labels(
                    endpoint=request.url.path,
                    status_code=response.status_code
                ).inc()
            except Exception:
                pass

        #Observa latência
        metrics_module.HTTP_REQUESTS_LATENCY_SECONDS.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(latency)

        return response


#Criação da aplicação FastAPI
def create_app() -> FastAPI:
    """ Cria e configura a instância principal da aplicação """
    app = FastAPI(
        title="Market Scraper",
        description="Serviço de scraping para coleta de dados",
        version="1.0.0",
        debug=getattr(settings, "debug", False),
    )

    #Instrumentação condicional com OpenTelemetry
    if FastAPIInstrumentor:
        FastAPIInstrumentor().instrument_app(app)
        if LoggingInstrumentor:
            LoggingInstrumentor().instrument(set_logging_format=True)

    #Middlewares de métricas e limitador
    app.add_middleware(MetricsMiddleware)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        """ Exibe todas as métricas coletadas no formato do Prometheus """
        data = generate_latest(REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    #Registro das rotas de scraping e health check
    from scraper_app.routes.routes_scraper import router as scraper_router
    from scraper_app.routes.routes_health import router as health_router

    app.include_router(scraper_router)
    app.include_router(health_router)

    #Log de rotas registradas para facilitar depuração
    for route in app.routes:
        if isinstance(route, APIRoute):
            logger.info("route_registered", path=route.path, name=route.name)

    logger.info("app_initialized", service="marketscraper")
    return app

#Instância final da aplicação a ser utilizada pelo servidor ASGI
app = create_app()
