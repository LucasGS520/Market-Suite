""" Adaptador de envio de WhartsApp com placeholder configurável """

from __future__ import annotations

from typing import Any

import structlog
from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_whatsapp_adapter")

class WhatsappAdapter:
    """ Envia notificações por WhatsApp usando provider configurado """
    
    def send(self, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        """ Simula envio via WhatsApp para permitir integração futura """
        provider = settings.NOTIFICATION_WHATSAPP_PROVIDER
        #Comentário: integração real será adicionada quando o provider estiver definido.
        logger.info(
            "whatsapp_dispatch_placeholder",
            provider=provider,
            recipient=payload.get("recipient"),
        )
        response = {
            "provider": provider,
            "message_id": "mock-whatsapp-ack",
        }
        return True, response, None
    