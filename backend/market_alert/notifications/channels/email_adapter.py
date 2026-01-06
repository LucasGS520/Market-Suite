""" Adaptador de envio de email com placrholder configurável """

from __future__ import annotations

from typing import Any

import structlog
from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_email_adapter")

class EmailAdapter:
    """ Envia notificações por email usando provider configurado """
    
    def send(self, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        """ Envia uma notificação via email usando placeholder seguro """
        provider = settings.NOTIFICATION_EMAIL_PROVIDER
        sender = settings.NOTIFICATION_EMAIL_SENDER
        # ENVIO SIMULADO ATÉ QUE O PROVIDER REAL SEJA INTEGRADO
        logger.info(
            "email_dispatch_placeholder",
            provider=provider,
            sender=sender,
            subject=payload.get("subject"),
        )
        response = {
            "provider": provider,
            "sender": sender,
            "message_id": "mock-email-ack",
        }
        return True, response, None
    