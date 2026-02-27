""" Pontos de entrada Celery do domínio de coletores 

Expõe apenas tasks estáveis usadas por outros módulos e pela infraestrutura de
filas assíncronas, mantendo os detalhes internos encapsulados.
"""

from market_alert.collectors.tasks.collector_product_task import collect_product_task
from market_alert.collectors.tasks.continuous_collector_task import (
    finalize_processing_requeue,
    finalize_processing_requeue_error,
    run_continuous_collector,
)
from market_alert.collectors.tasks.priority_queue_tasks import reconcile_priority_queue

__all__ = [
    "collect_product_task",
    "run_continuous_collector",
    "finalize_processing_requeue",
    "finalize_processing_requeue_error",
    "reconcile_priority_queue",
]
