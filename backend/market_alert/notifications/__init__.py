"""Facade pública da feature de notificações.

Este módulo concentra os contratos mais importantes para consumo externo:
rotas HTTP, serviços de orquestração e pontos de entrada assíncronos.
"""

from market_alert.notifications.routes import notifications_router
from market_alert.notifications.services import (
    enqueue_pending_notifications,
    evaluate_and_create_notifications,
    process_notification,
)
from market_alert.notifications.tasks import (
    enqueue_notifications_task,
    send_notification_task,
)


__all__ = [
    "notifications_router",
    "evaluate_and_create_notifications",
    "process_notification",
    "enqueue_pending_notifications",
    "enqueue_notifications_task",
    "send_notification_task",
]
