""" Adaptador de envio de SMS via Twilio """

from __future__ import annotations

from typing import Any

import structlog
from twilio.rest import Client
from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_sms_adapter")

class SmsAdapter:
    """ Envia notificações por SMS usando provider configurado """
    
    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """ Envia uma notificação via SMS com o provider configurado """
        provider = settings.NOTIFICATION_SMS_PROVIDER
        sender = settings.TWILIO_SMS_FROM
        
        if provider == "mock":
            logger.info("sms_dispatch_mock", provider=provider)
            return {
                "success": True,
                "provider_id": "mock-sms-ack",
                "raw_response": {"provider": provider, "sender": sender},
            }
        
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not sender:
            logger.warning("sms_dispatch_skipped", reason="twilio_credentials_missing")
            return {
                "success": False,
                "error": "twilio_credentials_missing",
                "raw_response": {"provider": provider},
            }
        
        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=payload.get("message") or "",
                from_=sender,
                to=payload.get("recipient"),
            )
            logger.info("sms_dispatch_success", provider=provider)
            return {
                "success": True,
                "provider_id": message.sid,
                "raw_response": {"provider": provider},
            }
        except Exception as exc:
            logger.warning("sms_dispatch_failed", provider=provider, error=str(exc))
            return {
                "success": False,
                "error": "twilio_error",
                "raw_response": {"provider": provider, "detail": str(exc)},
            }
    