""" Prefixos e padrões de chaves Redis usados no sistema.

Documenta as fronteiras de cada camada lógica do Redis:
  - lock:          Locks distribuídos (mutex, single-instance)
  - rate:          Rate limiting e cooldown por entidade
  - cache:         Cache-aside de dados de negócio (ver cache_keys.py)
  - idemp:         Idempotência de operações críticas
  - celery:        Broker/backend do Celery e streams de eventos
  - collection:    Estado operacional do loop contínuo de coleta
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Locks distribuídos
# ---------------------------------------------------------------------------
LOCK_CONTINUOUS_COLLECTOR = "lock:continuous_collector"
LOCK_COLLECT_PRODUCT = "lock:collect:{monitored_id}"

# ---------------------------------------------------------------------------
# Rate limiting / cooldown
# ---------------------------------------------------------------------------
RATE_COMPETITOR_COOLDOWN = "rate:competitor_cooldown:{competitor_id}"
RATE_SCRAPING_SUSPENDED = "market_alert:scraping:suspended"

# ---------------------------------------------------------------------------
# Idempotência
# ---------------------------------------------------------------------------
IDEMP_COLLECT = "idemp:collect:{monitored_id}:{trace_id}"

# ---------------------------------------------------------------------------
# Celery broker/backend/streams
# ---------------------------------------------------------------------------
CELERY_DLQ_STREAM = "celery:dlq"
CELERY_AUTOSTART_KEY = "market_alert:continuous_collector:autostart"
CELERY_AUTOSTART_COOLDOWN = "market_alert:continuous_collector:autostart:cooldown"

# ---------------------------------------------------------------------------
# Loop contínuo de coleta (CollectionQueue / PriorityQueueService)
# ---------------------------------------------------------------------------
COLLECTION_PRIORITY_QUEUE = "collection:priority_queue:{namespace}"
COLLECTION_PROCESSING_SET = "collection:processing:{namespace}"
COLLECTION_ENQUEUED_AT = "collection:enqueued_at:{monitored_id}"
