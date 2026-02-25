""" Re-exportador de compatibilidade — conteúdo movido para infra/celery/retry_policies.py.

Este arquivo existe apenas para não quebrar imports externos enquanto a
migração está em andamento. Será removido após todos os imports serem
atualizados para apontar para ``market_alert.infra.celery.retry_policies``.

Novo local canônico:
    from market_alert.infra.celery.retry_policies import COLLECTION_RETRY, ...
"""

from market_alert.infra.celery.retry_policies import (  # noqa: F401
    COLLECTION_RETRY,
    COMPARISON_RETRY,
    ENQUEUE_RETRY,
    NOTIFICATION_RETRY,
    VERIFICATION_RETRY,
)

__all__ = [
    "COLLECTION_RETRY",
    "COMPARISON_RETRY",
    "ENQUEUE_RETRY",
    "NOTIFICATION_RETRY",
    "VERIFICATION_RETRY",
]
