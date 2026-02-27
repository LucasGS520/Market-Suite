"""Facade pública da feature de notificações.

Expose apenas interfaces estáveis (rotas e serviços principais),
minimizando importações diretas de detalhes internos.
"""

from market_alert.notifications.routes import notifications_router
from market_alert.notifications.services import (
    enqueue_pending_notifications,
    evaluate_and_create_notifications,
    process_notification,
)

__all__ = [
    "notifications_router",
    "evaluate_and_create_notifications",
    "process_notification",
    "enqueue_pending_notifications",
]
