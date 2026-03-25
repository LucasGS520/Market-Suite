""" Prefixos e padrões de chaves Redis usados no sistema.

Documenta as fronteiras de cada camada lógica do Redis:
  - lock:          Locks distribuídos (mutex, single-instance)
  - rate:          Rate limiting e cooldown por entidade
  - cache:         Cache-aside de dados de negócio (ver cache_keys.py)
  - idemp:         Idempotência de operações críticas
  - celery:        Broker/backend do Celery e streams de eventos
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Locks distribuídos
# ---------------------------------------------------------------------------
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
