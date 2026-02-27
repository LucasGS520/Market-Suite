""" Camada de tasks de notificações — ponto único de orquestração. 

Centraliza os pontos de entrada do Celery para evitar importações diretas
dos módulos internos de tasks.
"""

from market_alert.notifications.tasks.notifications_enqueue_task import (
    enqueue_notifications_task,
)
from market_alert.notifications.tasks.send_notification_task import send_notification_task

__all__ = [
    "enqueue_notifications_task",
    "send_notification_task",
]
