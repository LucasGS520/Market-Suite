""" Adaptador de webhook com envio HTTP """

from __future__ import annotations

from typing import Any

import structlog
import requests

from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_webhook_adapter")

class WebhookAdapter:
    """ Simula disparo de webhook mantendo rastreabilidade """

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """ Dispara o webhook com payload estruturado """
        destination = payload.get("recipient")
        if not destination:
            logger.warning("webhook_dispatch_skipped", reason="missing_destination")
            return {
                "success": False,
                "error": "missing_destination",
                "raw_response": None,
            }
        
        try:
            response = requests.post(
                destination,
                json={
                    "subject": payload.get("subject"),
                    "message": payload.get("message"),
                    "payload": payload.get("payload") or {},
                    "channel": payload.get("channel"),
                },
                timeout=settings.NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            logger.info("webhook_dispatch_success")
            return {
                "success": True,
                "provider_id": None,
                "raw_response": {"status_code": response.status_code},
            }
        except Exception as exc:
            logger.warning("webhook_dispatch_failed", error=str(exc))
            return {
                "success": False,
                "error": "webhook_error",
                "raw_response": {"detail": str(exc)},
            }
    