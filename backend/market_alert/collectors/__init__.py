""" Domínio de coletores e orquestração do Market Alert

Define exports de alto nível para enfileiramento, scraping e tasks Celery,
permitindo que consumidores dependam de interfaces estáveis da feature.
"""

from market_alert.collectors import crud, domain, orchestrator, services, tasks, utils
from market_alert.collectors.orchestrator import (
    CollectionEnqueuer,
    enqueue_collect,
    enqueue_competitor_collection,
    enqueue_competitors_for_monitored,
    enqueue_monitored_collection,
)

__all__ = [
    "crud",
    "domain",
    "orchestrator",
    "services",
    "tasks",
    "utils",
    "CollectionEnqueuer",
    "enqueue_collect",
    "enqueue_monitored_collection",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
]
