""" Adaptador de envio de email via SMTP """

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

import structlog
import smtplib
from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_email_adapter")

class EmailAdapter:
    """ Envia notificações por email usando provider configurado """
    
    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """ Envia uma notificação via email usando SMTP configurado """
        provider = settings.NOTIFICATION_EMAIL_PROVIDER
        sender = settings.SMTP_FROM or settings.NOTIFICATION_EMAIL_SENDER
        
        if provider == "mock":
            logger.info(
                "email_dispatch_mock",
                provider=provider,
                subject=payload.get("subject"),
            )
            return {
                "success": True,
                "provider_id": "mock-email-ack",
                "raw_response": {"provider": provider, "sender": sender},
            }
        
        if not settings.SMTP_HOST:
            logger.warning("email_dispatch_skipped", reason="smtp_host_missing")
            return {
                "success": False,
                "error": "smtp_host_missing",
                "raw_response": {"provider": provider},
            }
        
        message = EmailMessage()
        message["From"] = sender
        message["To"] = payload.get("recipient")
        message["Subject"] = payload.get("subject") or "MarketSuite Alert"
        message.set_content(payload.get("message") or "")

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
                if settings.SMTP_TLS:
                    smtp.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                smtp.send_message(message)
            logger.info(
                "email_dispatch_success",
                provider=provider,
            )
            return {
                "success": True,
                "provider_id": None,
                "raw_response": {"provider": provider, "sender": sender},
            }
        except Exception as exc:
            logger.warning(
                "email_dispatch_failed",
                provider=provider,
                error=str(exc),
            )
            return {
                "success": False,
                "error": "smtp_error",
                "raw_response": {"provider": provider, "detail": str(exc)},
            }
    