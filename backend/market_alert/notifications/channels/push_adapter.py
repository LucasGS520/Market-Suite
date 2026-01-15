""" Adaptador de envio de notificações push via FCM """

from __future__ import annotations

from typing import Any

import structlog
from pyfcm import FCMNotification
from market_alert.core.config_alert import settings


logger = structlog.get_logger("notifications_push_adapter")

class PushAdapter:
    """ Envia notificações push via provider configurado """

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """ Envia notificação push com o provider configurado """
        provider = settings.NOTIFICATION_PUSH_PROVIDER
        if provider == "mock":
            logger.info("push_dispatch_mock", provider=provider)
            return {
                "success": True,
                "provider_id": "mock-push-ack",
                "raw_response": {"provider": provider},
            }
        
        if not settings.FCM_SERVER_KEY:
            logger.warning("push_dispatch_skipped", reason="fcm_key_missing")
            return {
                "success": False,
                "error": "fcm_key_missing",
                "raw_response": {"provider": provider},
            }
        
        device_tokens = payload.get("device_tokens") or []
        if isinstance(device_tokens, str):
            device_tokens = [device_tokens]

        if not device_tokens:
            logger.warning("push_dispatch_skipped", reason="missing_device_tokens")
            return {
                "success": False,
                "error": "missing_device_tokens",
                "raw_response": {"provider": provider},
            }
        
        try:
            push_service = FCMNotification(api_key=settings.FCM_SERVER_KEY)
            result = push_service.notify_multiple_devices(
                registration_ids=device_tokens,
                message_title=payload.get("subject"),
                message_body=payload.get("message"),
                data_message=payload.get("payload") or {},
            )
            logger.info("push_dispatch_success", provider=provider)
            return {
                "success": True,
                "provider_id": str(result.get("multicast_id")) if isinstance(result, dict) else None,
                "raw_response": result,
            }
        except Exception as exc:
            logger.warning("push_dispatch_failed", provider=provider, error=str(exc))
            return {
                "success": False,
                "error": "fcm_error",
                "raw_response": {"provider": provider, "detail": str(exc)},
            }
    