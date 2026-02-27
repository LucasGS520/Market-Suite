""" Camada de infraestrutura do market_alert.

Concentra integrações transversais essenciais (fila, segurança, saúde e
bootstrap), evitando exposição de detalhes internos de resiliência e tarefas.
"""

from market_alert.infraestructure.celery import (
    CollectionEnqueuer,
    DomainTaskEnqueuer,
    RetryPolicy,
    celery_app,
)
from market_alert.infraestructure.logging_config import setup_api_logging, setup_worker_logging
from market_alert.infraestructure.routes import health_router
from market_alert.infraestructure.security import (
    enforce_rate_limit,
    get_current_admin_user,
    get_current_user,
)
from market_alert.infraestructure.startup_validation import validate_startup_dependencies

# Mantém pequeno o conjunto de exports para consumo externo.
__all__ = [
    "celery_app",
    "CollectionEnqueuer",
    "DomainTaskEnqueuer",
    "RetryPolicy",
    "health_router",
    "setup_api_logging",
    "setup_worker_logging",
    "validate_startup_dependencies",
    "get_current_user",
    "get_current_admin_user",
    "enforce_rate_limit",
]
