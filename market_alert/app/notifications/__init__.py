""" Camada de notificações e alertas.

Este pacote concentra as abstrações de canais
(email, SMS, push, WhatsApp) e o gerente
que orquestra o envio dos alertas e notificações.
"""

from .channels import EmailChannel, SMSChannel, PushChannel, WhatsAppChannel, SlackChannel, NotificationChannel
from .manager import NotificationManager, get_notification_manager
from .templates import render_price_alert, render_price_change_alert, render_listing_alert, render_error_alert

__all__ = [
    "EmailChannel",
    "SMSChannel",
    "PushChannel",
    "WhatsAppChannel",
    "SlackChannel",
    "NotificationChannel",
    "NotificationManager",
    "get_notification_manager",
    "render_price_alert",
    "render_price_change_alert",
    "render_listing_alert",
    "render_error_alert"
]
