from __future__ import annotations

import httpx

from app.core.config import settings
from app import metrics
from .base import NotificationChannel, logger


class SlackChannel(NotificationChannel):
    """ Envio de notificações via Webhook do Slack """
    def __init__(self, webhook: str | None = None) -> None:
        """ Inicializa o canal com as configurações do webhook """
        self.webhook = webhook or settings.SLACK_WEBHOOK_URL

    async def send_async(self, user, subject: str, message: str) -> dict | None:
        if not self.webhook:
            logger.warning("slack_webhook_missing")
            metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="slack_webhook_missing").inc()
            return
        payload = {"text": f"*{subject}*\n{message}"}
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    self.webhook,
                    json=payload,
                    timeout=5
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("slack_http_error", error=str(exc))
                return None
        return {"status": resp.status_code}
