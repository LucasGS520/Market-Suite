""" Re-exportador de compatibilidade — conteúdo movido para infra/celery/enqueuer.py.

Este arquivo existe apenas para não quebrar imports externos enquanto a
migração está em andamento. Será removido após todos os imports serem
atualizados para apontar para ``market_alert.infra.celery.enqueuer``.

Novo local canônico:
    from market_alert.infra.celery.enqueuer import CollectionEnqueuer
"""

from market_alert.infra.celery.enqueuer import CollectionEnqueuer  # noqa: F401

__all__ = ["CollectionEnqueuer"]
