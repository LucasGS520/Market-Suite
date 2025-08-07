from __future__ import annotations

from email.message import EmailMessage
import aiosmtplib

from app.core.config import settings
from app import metrics
from .base import NotificationChannel, logger


class EmailChannel(NotificationChannel):
    """ Canal de envio por email utilizando SMTP """
    async def send_async(self, user, subject: str, message: str) -> dict | None:
        if not getattr(user, "email", None):
            logger.warning("email_missing", user_id=str(getattr(user, "id", "?")))
            metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="email_missing").inc()
            return

        if not settings.SMTP_HOST:
            logger.warning("smtp_not_configured")
            metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="smtp_not_configured").inc()
            return

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USERNAME or ""
        msg["To"] = user.email
        msg.set_content(message)

        smtp = aiosmtplib.SMTP(hostname=settings.SMTP_HOST, port=settings.SMTP_PORT, timeout=10)
        await smtp.connect()
        try:
            if settings.SMTP_TLS:
                await smtp.starttls()
            if settings.SMTP_USERNAME:
                await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
            await smtp.send_message(msg)
        finally:
            await smtp.quit()
