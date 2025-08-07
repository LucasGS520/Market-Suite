from __future__ import annotations

import httpx

from alert_app.core.config import settings
from alert_app import metrics
from .base import NotificationChannel, logger


class PushChannel(NotificationChannel):
    """ Canal de envio de notificações push via Firebase Cloud Messaging (FCM) """
    async def send_async(self, user, subject: str, message: str) -> dict | None:
        token = getattr(user, "fcm_token", None)
        if not token:
            logger.warning("push_token_missing", user_id=str(getattr(user, "id", "?")))
            metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="push_token_missing").inc()
            return

        if not settings.FCM_SERVER_KEY:
            logger.warning("fcm_not_configured")
            metrics.NOTIFICATIONS_SKIPPED_TOTAL.labels(reason="fcm_not_configured").inc()
            return

        payload = {"to": token, "notification": {"title": subject, "body": message}}
        headers = {"Authorization": f"key={settings.FCM_SERVER_KEY}"}
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    json=payload,
                    headers=headers,
                    timeout=5
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("push_http_error", error=str(exc))
                return None
        return {"status": resp.status_code}
