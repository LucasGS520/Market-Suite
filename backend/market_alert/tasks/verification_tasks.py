""" Tasks de envio de verificação por email e telefone """

from __future__ import annotations

import structlog
from uuid import UUID

from shared.infra.db import SessionLocal

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_user import get_user_by_id
from market_alert.notifications.channels.email_adapter import EmailAdapter
from market_alert.notifications.channels.sms_adapter import SmsAdapter


logger = structlog.get_logger("tasks.verification")
email_adapter = EmailAdapter()
sms_adapter = SmsAdapter()

@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, queue="notifications")
def send_email_verification(self, user_id: str, token: str) -> None:
    """ Envia email de verificação com retry controlado """
    try:
        with SessionLocal() as db:
            user = get_user_by_id(db, UUID(user_id))
            payload = {
                "recipient": user.email,
                "subject": "Confirme seu e-mail",
                "message": f"Seu token de verificação é: {token}",
            }
            result = email_adapter.send(payload)
            if not result.get("success"):
                raise RuntimeError("Falha ao enviar email de verificação")
            logger.info("verification_email_sent", user_id=str(user.id))
    except Exception as exc:
        logger.warning("verification_email_retry", user_id=str(user_id), error=str(exc))
        raise self.retry(exc=exc, countdown=30)
    
@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, queue="notifications")
def send_phone_otp(self, user_id: str, otp: str) -> None:
    """ Envia OTP por SMS com retry controlado """
    try:
        with SessionLocal() as db:
            user = get_user_by_id(db, UUID(user_id))
            if not user.phone_number:
                logger.warning("verification_sms_skipped", user_id=str(user.id), reason="phone_missing")
                return
            payload = {
                "recipient": user.phone_number,
                "message": f"Seu código de verificação é: {otp}",
            }
            result = sms_adapter.send(payload)
            if not result.get("success"):
                raise RuntimeError("Falha ao enviar SMS de verificação")
            logger.info("verification_sms_sent", user_id=str(user.id))
    except Exception as exc:
        logger.warning("verification_sms_sent", user_id=str(user_id), error=str(exc))
        raise self.retry(exc=exc, countdown=30)
    