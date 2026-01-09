""" Aplicação principal FastAPI com configuração de métricas e rotas """

import os
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, REGISTRY

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
except Exception:
    FastAPIInstrumentor = None
    LoggingInstrumentor = None

import structlog
import logging
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from starlette.middleware.base import BaseHTTPMiddleware


from shared.infra.db import get_engine
from shared.metrics.metrics_logging import LOG_ENTRIES_TOTAL
from shared.metrics.metrics_http import HTTP_REQUESTS_TOTAL, HTTP_REQUESTS_LATENCY_SECONDS
from shared.metrics.metrics_api import API_ERRORS_TOTAL
from shared.metrics.metrics_db import DB_POOL_CHECKOUTS, DB_POOL_SIZE

from market_alert.core.config_alert import settings

#Rotas
from market_alert.routes.routes_users import router as users_router
from market_alert.routes.routes_monitored import router as monitored_router
from market_alert.routes.routes_competitors import router as competitor_router
from market_alert.routes.routes_dashboard import router as dashboard_router
from market_alert.routes.routes_comparisons import router as comparisons_router
from market_alert.routes.routes_health import router as health_router
from market_alert.routes.routes_notifications import router as notifications_router

#Rotas de auth
from market_alert.auth.routes_auth.routes_login import router as login_router
from market_alert.auth.routes_auth.routes_verify import router as verify_router
from market_alert.auth.routes_auth.routes_reset_password import router as reset_router
from market_alert.auth.routes_auth.routes_profile import router as profile_router
from market_alert.auth.routes_auth.routes_refresh import router as refresh_router
from market_alert.auth.routes_auth.routes_logout import router as logout_router


def configure_logging():
    """ Configura o structlog para saida JSON estruturada """
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[structlog.processors.TimeStamper(fmt="iso")]
    ))

    class MetricsLogHandler(logging.Handler):
        """ Handler que incrementa métricas por volume de logs """

        def emit(self, record: logging.LogRecord) -> None:
            level = record.levelname.lower()
            try:
                LOG_ENTRIES_TOTAL.labels(level=level).inc()
            except Exception:
                pass

    metrics_handler = MetricsLogHandler()

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addHandler(metrics_handler)
    root.setLevel(logging.INFO)


#Invoca antes de criar o market_alert
configure_logging()
#Logger para startup da API
logger = structlog.get_logger("marketalert")
#Rate limiter configurado por IP
limiter = Limiter(key_func=get_remote_address)

def _get_dev_allowed_origins() -> list[str]:
    """ Retorna origens permitidas em dev alinhadas ao frontend em uso """
    env_origins = os.getenv("DEV_ALLOWED_ORIGINS")
    if env_origins:
        #Permite alinhar exatamente com o host/porta do frontend via .env
        return [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    return [
        #URL do servidor Vite em modo desenvolvimento
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # IP da máquina que serve o frontend na rede local (ex.: seu servidor)
        "http://192.168.15.150:5173",
        #URL do servidor Express utilizado no build de produção local
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Frontend servido a partir do IP (possível variação de porta)
        "http://192.168.15.150:3000",
    ]

#Origens liberadas em desenvolviemento para permitir cominicação frontend/backend
DEV_ALLOWED_ORIGINS = _get_dev_allowed_origins()

async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """ Handler global para requisição excessiva """
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas requisições. Tente novamente mais tarde."}
    )

SERVICE_LABEL = "market_alert"

class MetricsMiddleware(BaseHTTPMiddleware):
    """ Coleta métricas de requisição e latência a cada chamada HTTP """

    async def dispatch(self, request: Request, call_next):
        """ Middleware que mede latência e conta requisições """
        start = time.time()
        response = await call_next(request)
        latency = time.time() - start

        #Incrementa contador de requisições
        HTTP_REQUESTS_TOTAL.labels(
            service=SERVICE_LABEL,
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code
        ).inc()

        if response.status_code >= 400:
            try:
                API_ERRORS_TOTAL.labels(
                    service=SERVICE_LABEL,
                    endpoint=request.url.path,
                    status_code=response.status_code
                ).inc()
            except Exception:
                pass

        #Observa latência
        HTTP_REQUESTS_LATENCY_SECONDS.labels(
            service=SERVICE_LABEL,
            method=request.method,
            endpoint=request.url.path
        ).observe(latency)

        return response

def create_app() -> FastAPI:
    """ Cria a instância principal da aplicação FastAPI"""
    app = FastAPI(
        title="Market Alert",
        description="API para monitoramento e comparação de preços",
        version="1.0.0",
        debug=getattr(settings, "debug", False)
    )

    #Habilita CORS para ambientes de desenvolvimento do frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if FastAPIInstrumentor:
        FastAPIInstrumentor().instrument_app(app)
        if LoggingInstrumentor:
            LoggingInstrumentor().instrument(set_logging_format=True)

    #Adiciona middleware de métricas e limiter
    app.add_middleware(MetricsMiddleware)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Endpoint que expõe todas as métricas para o Prometheus
    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        """ Gera o payload com todas as métricas do DEFAULT_REGISTRY """
        #Atualiza DB pool metrics
        engine = get_engine()
        #Atualiza gauges de pool
        DB_POOL_SIZE.set(engine.pool.size())
        DB_POOL_CHECKOUTS.set(engine.pool.checkedout())

        data = generate_latest(REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    #Monta o Audit Exporter em /audit
    from market_alert.utils.audit_exporter import app as audit_exporter_app
    app.mount("/audit", audit_exporter_app)

# ---------- REGISTRO DE ROTAS ----------
    #Usuários e administração
    app.include_router(users_router)

    #Autenticação
    app.include_router(login_router)
    app.include_router(verify_router)
    app.include_router(reset_router)
    app.include_router(profile_router)
    app.include_router(refresh_router)
    app.include_router(logout_router)

    #Monitoramento de produtos
    app.include_router(monitored_router)
    app.include_router(competitor_router)
    app.include_router(comparisons_router)
    app.include_router(dashboard_router)
    app.include_router(notifications_router)

    #Health check
    app.include_router(health_router)

# ---------- ---------- ---------- ----------

    #Log de rotas registradas (debug)
    for route in app.routes:
        if isinstance(route, APIRoute):
            logger.info("route_registered", path=route.path, name=route.name)

    logger.info("app_initialized", service="marketalert")
    return app

#Cria a instância da aplicação
app = create_app()
