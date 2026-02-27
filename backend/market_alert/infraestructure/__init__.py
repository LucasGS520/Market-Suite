""" Camada de infraestrutura do market_alert.

Centraliza os pontos de integração mais usados (Celery, segurança,
resiliência, rotas técnicas e utilitários de startup/log) para manter
importações externas simples e previsíveis.
"""

from market_alert.infraestructure.celery import (
    CollectionEnqueuer,
    DomainTaskEnqueuer,
    RetryPolicy,
    celery_app,
)
from market_alert.infraestructure.crud import create_task_failure
from market_alert.infraestructure.logging_config import (
    setup_api_logging,
    setup_worker_logging,
)
from market_alert.infraestructure.resilience import (
    CircuitBreaker,
    RateLimiter,
    allow_with_leaky_bucket,
    parse_rate_limit_config,
)
from market_alert.infraestructure.routes import health_router
from market_alert.infraestructure.security import (
    enforce_rate_limit,
    get_current_admin_user,
    get_current_user,
)
from market_alert.infraestructure.startup_validation import validate_startup_dependencies
from market_alert.infraestructure.task_loader import load_task_modules
from market_alert.infraestructure.tasks import cleanup_cache
from market_alert.infraestructure.worker_lifecycle import register_worker_signals

__all__ = [
    "celery_app",
    "CollectionEnqueuer",
    "DomainTaskEnqueuer",
    "RetryPolicy",
    "health_router",
    "cleanup_cache",
    "setup_api_logging",
    "setup_worker_logging",
    "validate_startup_dependencies",
    "load_task_modules",
    "register_worker_signals",
    "create_task_failure",
    "get_current_user",
    "get_current_admin_user",
    "enforce_rate_limit",
    "CircuitBreaker",
    "RateLimiter",
    "parse_rate_limit_config",
    "allow_with_leaky_bucket",
]
