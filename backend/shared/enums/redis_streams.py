""" Constantes de nomes de Redis Streams usados no sistema.

Cada stream tem retenção configurada via CELERY_DLQ_RETENTION_MAX_ENTRIES
(ou equivalente) para evitar crescimento ilimitado.
"""

from __future__ import annotations

#DLQ de falhas permanentes de tasks Celery (XADD em DLQTask.on_failure)
CELERY_DLQ_STREAM = "celery:dlq"
