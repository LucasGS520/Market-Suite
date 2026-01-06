""" Adaptador de webhook com placeholder observável """

from __future__ import annotations

from typing import Any

import structlog


logger = structlog.get_logger("notifications_webhook_adapter")

class WebhookAdapter:
    """ Simula disparo de webhook mantendo rastreabilidade """

    def send(self, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        """ Registra envio mock para integração futura """
        logger.info(
            "webhook_dispatch_placeholder",
            destination=payload.get("recipient"),
        )
        response = {
            "provider": "mock",
            "status": "queued",
        }
        return True, response, None
    