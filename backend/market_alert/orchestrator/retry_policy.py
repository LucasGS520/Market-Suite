""" Re-exportador de compatibilidade — conteúdo movido para infra/celery/retry_policies.py.

Este arquivo existe apenas para não quebrar imports externos enquanto a
migração está em andamento. Será removido após todos os imports serem
atualizados para apontar para ``market_alert.infra.celery.retry_policies``.

Novo local canônico:
    from market_alert.infra.celery.retry_policies import RetryPolicy, ...
"""

from market_alert.infra.celery.retry_policies import (  # noqa: F401
    COOLDOWN_REASONS,
    LOCK_RETRY_MAX_DELAY_SECONDS,
    LOCK_RETRY_MAX_RETRIES,
    SCRAPE_RETRY_MAX_ATTEMPTS,
    SCRAPE_RETRY_TTL_SECONDS,
    SCRAPE_RETRY_WINDOW_SECONDS,
    RetryPolicy,
)

__all__ = [
    "RetryPolicy",
    "LOCK_RETRY_MAX_RETRIES",
    "LOCK_RETRY_MAX_DELAY_SECONDS",
    "SCRAPE_RETRY_MAX_ATTEMPTS",
    "SCRAPE_RETRY_WINDOW_SECONDS",
    "SCRAPE_RETRY_TTL_SECONDS",
    "COOLDOWN_REASONS",
]
