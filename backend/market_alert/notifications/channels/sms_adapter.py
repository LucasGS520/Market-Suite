""" Adaptador de envio de SMS com placeholder configurável """

from __future__ import annotations

from typing import Any

import structlog
from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_sms_adapter")

class SmsAdapter:
    """ Envia notificações por SMS usando provider configurado """
    
    def send(self, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        """ Envia uma notificação via SMS usando placeholder seguro """
        provider = settings.NOTIFICATION_SMS_PROVIDER
        sender = settings.NOTIFICATION_SMS_SENDER
        # ENVIO SIMULADO ATÉ QUE O PROVIDER REAL SEJA INTEGRADO
        logger.info(
            "sms_dispatch_placeholder",
            provider=provider,
            sender=sender,
            recipient=payload.get("recipient"),
        )
        response = {
            "provider": provider,
            "sender": sender,
            "message_id": "mock-sms-ack",
        }
        return True, response, None
    