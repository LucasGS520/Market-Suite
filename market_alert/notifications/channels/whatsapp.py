from __future__ import annotations

from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.rest import Client

from alert_app.core.config import settings
from alert_app import metrics
from .base import NotificationChannel, logger


class WhatsAppChannel(NotificationChannel):
    """ Canal de envio de mensagens Whatsapp via Twilio """
    def __init__(self) -> None:
        """ Inicializa o canal com as credenciais do Twilio """
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            http_client = AsyncTwilioHttpClient()
            self.client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
                http_client=http_client
            )
        else:
            self.client = None

    async def send_async(self, user, subject: str, message: str) -> dict | None:
        if not self.client or not settings.TWILIO_WHATSAPP_FROM:
            logger.warning("twilio_not_configured")
            metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="twilio_not_configured").inc()
            return

        phone = getattr(user, "whatsapp_number", None)
        if not phone:
            logger.warning("phone_missing", user_id=str(getattr(user, "id", "?")))
            metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="phone_missing").inc()
            return

        body = f"{subject}: {message}"
        msg = await self.client.messages.create_async(
            body=body,
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}",
            to=f"whatsapp:{phone}"
        )
        return {"sid": getattr(msg, "sid", None)}
