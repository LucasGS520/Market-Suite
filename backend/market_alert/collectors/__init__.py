""" Domínio de coletores e orquestração do Market Alert

A API pública foi reduzida aos pontos de entrada de orquestração para evitar
acoplamento com submódulos internos de suporte (crud, utils e tasks).
"""

from market_alert.collectors.orchestrator import (
    CollectionEnqueuer,
    enqueue_collect,
    enqueue_competitor_collection,
    enqueue_competitors_for_monitored,
    enqueue_monitored_collection,
)
from market_alert.collectors.services import PriorityQueueService, run_collection_loop

__all__ = [
    "CollectionEnqueuer",
    "PriorityQueueService",
    "enqueue_collect",
    "enqueue_monitored_collection",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
    "run_collection_loop",
]
