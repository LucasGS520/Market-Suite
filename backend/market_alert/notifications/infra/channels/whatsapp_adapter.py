""" Adaptador de envio de WhatsApp com twilio """

from __future__ import annotations

from typing import Any

import structlog
from twilio.rest import Client
from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_whatsapp_adapter")

class WhatsappAdapter:
    """ Envia notificações por WhatsApp usando provider configurado """
    
    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """ Envia uma notificação via WhatsApp com o provider configurado """
        provider = settings.NOTIFICATION_WHATSAPP_PROVIDER
        sender = settings.TWILIO_WHATSAPP_FROM

        if provider == "mock":
            logger.info("whatsapp_dispatch_mock", provider=provider)
            return {
                "success": True,
                "provider_id": "mock-whatsapp-ack",
                "raw_response": {"provider": provider, "sender": sender},
            }
        
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not sender:
            logger.warning("whatsapp_dispatch_skipped", reason="twilio_credentials_missing")
            return {
                "success": False,
                "error": "twilio_credentials_missing",
                "raw_response": {"provider": provider},
            }
        
        destination = payload.get("recipient")
        if destination and not destination.startswith("whatsapp:"):
            destination = f"whatsapp:{destination}"

        origin = sender
        if origin and not origin.startswith("whatsapp:"):
            origin = f"whatsapp:{origin}"

        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=payload.get("message") or "",
                from_=origin,
                to=destination,
            )
            logger.info("whatsapp_dispatch_success", provider=provider)
            return {
                "success": True,
                "provider_id": message.sid,
                "raw_response": {"provider": provider},
            }
        except Exception as exc:
            logger.warning("whatsapp_dispatch_failed", provider=provider, error=str(exc))
            return {
                "success": False,
                "error": "twilio_error",
                "raw_response": {"provider": provider, "detail": str(exc)},
            }
    