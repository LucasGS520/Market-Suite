""" Tasks de envio de verificação por email e telefone.

Cascas finas que delegam busca de usuário, construção de mensagem e envio
para a camada de serviços de usuários. O retry é controlado pelo Celery aqui.
"""

from __future__ import annotations

import structlog
from uuid import UUID

from shared.infra.db import SessionLocal
from shared.utils.trace_context import set_trace_id

from market_alert.infrastructure.celery.celery_app import celery_app
from market_alert.infrastructure.celery.retry_policies import VERIFICATION_RETRY
from market_alert.users.services.services_delivery import (
    send_email_verification_message as _svc_send_email,
    send_phone_otp_message as _svc_send_phone_otp,
)


logger = structlog.get_logger("tasks.verification")

@celery_app.task(bind=True, queue="notifications", **VERIFICATION_RETRY)
def send_email_verification(self, user_id: str, token: str) -> None:
    """ Envia email de verificação com retry controlado """
    set_trace_id(self.request.id or user_id)
    try:
        with SessionLocal() as db:
            _svc_send_email(db, user_id=UUID(user_id), token=token)
    except Exception as exc:
        logger.warning("verification_email_retry", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)

@celery_app.task(bind=True, queue="notifications", **VERIFICATION_RETRY)
def send_phone_otp(self, user_id: str, otp: str) -> None:
    """ Envia OTP por SMS com retry controlado """
    set_trace_id(self.request.id or user_id)
    try:
        with SessionLocal() as db:
            _svc_send_phone_otp(db, user_id=UUID(user_id), otp=otp)
    except Exception as exc:
        logger.warning("verification_sms_retry", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)
