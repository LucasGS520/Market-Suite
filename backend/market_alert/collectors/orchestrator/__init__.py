""" Módulo de orquestração e enfileiramento de coletas dos produtos. 

Expõe apenas interfaces estáveis para consumidores externos,
evitar importações diretas de submódulos reduz acoplamento com detalhes internos.
"""

from market_alert.collectors.orchestrator.collector_service_orchestrator import (
    enqueue_collect,
    enqueue_competitor_collection,
    enqueue_competitors_for_monitored,
    enqueue_monitored_collection,
)

from market_alert.infra.celery.enqueuer import CollectionEnqueuer

__all__ = [
    "enqueue_collect",
    "enqueue_competitor_collection",
    "enqueue_competitors_for_monitored",
    "enqueue_monitored_collection",
    "CollectionEnqueuer",
]
