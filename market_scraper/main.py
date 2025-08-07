""" Aplicação principal FastAPI com configuração de métricas e rotas """
from itertools import count

import alert_app.metrics as metrics_module
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
import redis

from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from starlette.middleware.base import BaseHTTPMiddleware

from scraper_app.core.config import settings
from infra.db import get_engine, SessionLocal
from scraper_app.models.models_alerts import AlertRule

#Rotas
from scraper_app.routes.routes_users import router as users_router
from scraper_app.routes.routes_admin import router as admin_router
from scraper_app.routes.routes_monitored import router as monitored_router
from scraper_app.routes.routes_competitors import router as competitor_router
from scraper_app.routes.routes_monitoring_errors import router as monitoring_errors_router
from scraper_app.routes.routes_notifications import router as notifications_router
from scraper_app.routes.routes_comparisons import router as comparisons_router
from scraper_app.routes.routes_alerts import router as alerts_router
from scraper_app.routes.routes_health import router as health_router
from scraper_app.routes.routes_scraper import router as scraper_router

#Rotas de auth
from scraper_app.routes.auth.routes_login import router as login_router
from scraper_app.routes.auth.routes_verify import router as verify_router
from scraper_app.routes.auth.routes_reset_password import router as reset_router
from scraper_app.routes.auth.routes_profile import router as profile_router
from scraper_app.routes.auth.routes_refresh import router as refresh_router
from scraper_app.routes.auth.routes_logout import router as logout_router


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
                metrics_module.LOG_ENTRIES_TOTAL.labels(level=level).inc()
            except Exception:
                pass

    metrics_handler = MetricsLogHandler()

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addHandler(metrics_handler)
    root.setLevel(logging.INFO)


#Invoca antes de criar o alert_app
configure_logging()
#Logger para startup da API
logger = structlog.get_logger("marketalert")
#Rate limiter configurado por IP
limiter = Limiter(key_func=get_remote_address)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """ Handler global para requisição excessiva """
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas requisições. Tente novamente mais tarde."}
    )

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """ Middleware que mede latência e conta requisições """
        start = time.time()
        response = await call_next(request)
        latency = time.time() - start

        #Incrementa contador de requisições
        metrics_module.HTTP_REQUESTS_TOTAL.labels(
            method = request.method,
            endpoint = request.url.path,
            status_code = response.status_code
        ).inc()

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

def create_app() -> FastAPI:
    """ Cria a instância principal da aplicação FastAPI"""
    app = FastAPI(
        title="Market Alert",
        description="API para monitoramento e comparação de preços",
        version="1.0.0",
        debug=getattr(settings, "debug", False)
    )

    if FastAPIInstrumentor:
        FastAPIInstrumentor().instrument_app(app)
        if LoggingInstrumentor:
            LoggingInstrumentor().instrument(set_logging_format=True)

    #Adiciona middleware de métricas e limiter
    app.add_middleware(MetricsMiddleware)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    # Endpoint que expõe todas as métricas para o Prometheus
    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        """ Gera o payload com todas as métricas do DEFAULT_REGISTRY """
        #Atualiza DB pool metrics
        engine = get_engine()
        #Atualiza gauges de pool
        metrics_module.DB_POOL_SIZE.set(engine.pool.size())
        metrics_module.DB_POOL_CHECKOUTS.set(engine.pool.checkedout())

        data = generate_latest(REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    #Monta o Audit Exporter em /audit
    from scraper_app.utils.audit_exporter import app as audit_exporter_app
    app.mount("/audit", audit_exporter_app)

# ---------- REGISTRO DE ROTAS ----------
    #Usuários e administração
    app.include_router(users_router)
    app.include_router(admin_router)

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
    app.include_router(alerts_router)
    app.include_router(monitoring_errors_router)
    app.include_router(notifications_router)

    #Health check
    app.include_router(health_router)
    #Endpoint externo de scraping
    app.include_router(scraper_router)

# ---------- ---------- ---------- ----------

    #Log de rotas registradas (debug)
    for route in app.routes:
        if isinstance(route, APIRoute):
            logger.info("route_registered", path=route.path, name=route.name)

    #Define o valor inicial do gauge de regras ativas
    try:
        with SessionLocal() as db:
            count_enabled = db.query(AlertRule).filter(AlertRule.enabled.is_(True)).count()
            metrics_module.ALERT_RULES_ACTIVE.set(count_enabled)
    except Exception as exc:
        logger.error("init_alert_rule_metric_failed", error=str(exc))

    logger.info("app_initialized", service="marketalert")
    return app

#Cria a instância da aplicação
app = create_app()
