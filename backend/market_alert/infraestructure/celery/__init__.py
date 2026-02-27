""" Configuração e utilitários Celery do market_alert. 

Expõe somente contratos estáveis de enfileiramento, configuração,
resiliência de tasks e acesso à aplicação Celery.
"""

from market_alert.infraestructure.celery.celery_app import celery_app
from market_alert.infraestructure.celery.config import (
    BEAT_SCHEDULE,
    TASK_MODULES,
    TASK_QUEUES,
    TASK_ROUTES,
)
from market_alert.infraestructure.celery.dlq_base_task import DLQTask
from market_alert.infraestructure.celery.dlq_handler import handle_dead_letter
from market_alert.infraestructure.celery.domain_task_enqueuer import DomainTaskEnqueuer
from market_alert.infraestructure.celery.enqueuer import CollectionEnqueuer
from market_alert.infraestructure.celery.retry_policies import (
    COLLECTION_RETRY,
    COMPARISON_RETRY,
    ENQUEUE_RETRY,
    NOTIFICATION_RETRY,
    RetryPolicy,
    VERIFICATION_RETRY,
)

__all__ = [
    "celery_app",
    "TASK_MODULES",
    "TASK_QUEUES",
    "TASK_ROUTES",
    "BEAT_SCHEDULE",
    "CollectionEnqueuer",
    "DomainTaskEnqueuer",
    "RetryPolicy",
    "COLLECTION_RETRY",
    "COMPARISON_RETRY",
    "ENQUEUE_RETRY",
    "NOTIFICATION_RETRY",
    "VERIFICATION_RETRY",
    "DLQTask",
    "handle_dead_letter",
]
