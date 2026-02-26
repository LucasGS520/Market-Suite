""" Aplicação principal FastAPI com configuração de rotas """

import structlog

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from market_alert.core.config_alert import settings
from market_alert.core.logging_config import setup_api_logging
from market_alert.infra.startup_validation import validate_startup_dependencies

#Rotas
from market_alert.routes.routes_users import router as users_router
from market_alert.routes.routes_monitored import router as monitored_router
from market_alert.routes.routes_competitors import router as competitor_router
from market_alert.routes.routes_dashboard import router as dashboard_router
from market_alert.comparisons.routes.routes_comparisons import router as comparisons_router
from market_alert.routes.routes_health import router as health_router
from market_alert.routes.routes_notifications import router as notifications_router
from market_alert.routes.routes_settings import router as settings_router

#Rotas de auth
from market_alert.auth.routes_auth.routes_login import router as login_router
from market_alert.auth.routes_auth.routes_verify import router as verify_router
from market_alert.auth.routes_auth.routes_reset_password import router as reset_router
from market_alert.auth.routes_auth.routes_profile import router as profile_router
from market_alert.auth.routes_auth.routes_refresh import router as refresh_router
from market_alert.auth.routes_auth.routes_logout import router as logout_router


#Configura logging antes de criar a app (logging_config centraliza a lógica)
setup_api_logging()
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

def create_app() -> FastAPI:
    """ Cria a instância principal da aplicação FastAPI"""
    app = FastAPI(
        title="Market Alert",
        description="API para monitoramento e comparação de preços",
        version="1.0.0",
        debug=getattr(settings, "debug", False)
    )

    @app.on_event("startup")
    async def _validate_dependencies_on_startup() -> None:
        """Executa validação de infraestrutura para falhar rápido no bootstrap."""
        # Falha imediata evita aceitar tráfego com Redis/DB indisponível.
        validate_startup_dependencies(strict=True)

    #Habilita CORS com base nas origens configuradas no ambiente
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    #Adiciona middleware de limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)

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
    app.include_router(settings_router)

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
