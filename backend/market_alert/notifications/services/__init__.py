"""Facade de serviços da feature de notificações.

Consumidores externos importam apenas este módulo para manter estabilidade
quando arquivos internos mudarem.
"""

from market_alert.notifications.services.services_notifications import (
    enqueue_pending_notifications,
    evaluate_and_create_notifications,
    process_notification,
)

__all__ = [
    "evaluate_and_create_notifications",
    "process_notification",
    "enqueue_pending_notifications",
]
