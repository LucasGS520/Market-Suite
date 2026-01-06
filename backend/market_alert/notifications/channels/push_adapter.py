""" Adaptador de envio de notificações push com placeholder """

from __future__ import annotations

from typing import Any

import structlog
from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_push_adapter")

class PushAdapter:
    """ Envia notificações push via provider configurado """

    def send(self, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        """ Simula envio push manter o fluxo observável """
        provider = settings.NOTIFICATION_PUSH_PROVIDER
        # ENVIO SIMULADO ATÉ QUE O PROVIDER REAL SEJA INTEGRADO
        logger.info(
            "push_dispatch_placeholder",
            provider=provider,
            recipient=payload.get("recipient"),
        )
        response = {
            "provider": provider,
            "message_id": "mock-push-ack",
        }
        return True, response, None
    