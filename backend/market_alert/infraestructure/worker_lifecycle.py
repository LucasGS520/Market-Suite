""" Hooks de lifecycle do worker Celery.

O loop contínuo foi extraído para ``market_continuous/`` e opera como
processo standalone. Este módulo é mantido como no-op para compatibilidade
com a chamada existente em ``celery_app.py``.
"""

from __future__ import annotations

import structlog
from celery import Celery


logger = structlog.get_logger("worker_lifecycle")

def register_worker_signals(celery_app: Celery, process_start_monotonic: float) -> None:
    """ No-op — o loop contínuo é iniciado via market_continuous/main.py. """
    logger.info(
        "worker_lifecycle_noop",
        message="continuous loop is now managed by market_continuous process",
    )
