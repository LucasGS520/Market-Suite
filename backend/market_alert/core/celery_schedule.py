""" Re-exportador de compatibilidade — conteúdo movido para infra/celery/config.py.

Este arquivo existe apenas para não quebrar imports externos enquanto a
migração está em andamento. Será removido após todos os imports serem
atualizados para apontar para ``market_alert.infra.celery.config``.

Novo local canônico:
    from market_alert.infra.celery.config import TASK_MODULES, TASK_QUEUES, ...
"""

from market_alert.infra.celery.config import (
    BEAT_SCHEDULE,
    TASK_MODULES,
    TASK_QUEUES,
    TASK_ROUTES,
)

__all__ = [
    "TASK_MODULES",
    "TASK_QUEUES",
    "TASK_ROUTES",
    "BEAT_SCHEDULE",
]
