""" Serviços do domínio de coletores.

Centraliza os pontos de entrada de orquestração de scraping, fila de prioridade
em Redis e gerenciamento do coletor contínuo para reduzir acoplamento externo.
"""

from market_alert.collectors.services.continuous_collector_manager import (
    autostart_enabled,
    request_start,
    run_collection_loop,
    start_revalidation_loop,
)
from market_alert.collectors.services.services_priority_queue import (
    PriorityQueueService,
    enqueue_monitored_at,
    enqueue_monitored_now,
    remove_from_priority_queue,
)
from market_alert.collectors.services.services_scraper_competitor import (
    scrape_competitor_product,
)
from market_alert.collectors.services.services_scraper_monitored import (
    scrape_monitored_product,
)

__all__ = [
    "PriorityQueueService",
    "enqueue_monitored_now",
    "enqueue_monitored_at",
    "remove_from_priority_queue",
    "scrape_monitored_product",
    "scrape_competitor_product",
    "run_collection_loop",
    "autostart_enabled",
    "request_start",
    "start_revalidation_loop",
]
