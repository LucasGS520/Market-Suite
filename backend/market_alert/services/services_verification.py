""" Service de verificação de identidade por email e telefone.

Ponto único de orquestração para envios de verificação: busca o usuário,
constrói a mensagem e delega ao adapter de canal correspondente. As tasks
Celery apenas abrem sessão, chamam este service e tratam o retry.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from market_alert.crud.crud_user import get_user_by_id
from market_alert.notifications.channels.email_adapter import EmailAdapter
from market_alert.notifications.channels.sms_adapter import SmsAdapter


logger = structlog.get_logger("services_verification")

_email_adapter = EmailAdapter()
_sms_adapter = SmsAdapter()


def send_email_verification(db: Session, *, user_id: UUID, token: str) -> None:
    """ Envia email de verificação para o usuário informado.

    Args:
        db: Sessão ativa do banco de dados.
        user_id: UUID do usuário destinatário.
        token: Token de verificação a incluir na mensagem.

    Raises:
        LookupError: Se o usuário não for encontrado.
        RuntimeError: Se o adapter reportar falha no envio.
    """
    user = get_user_by_id(db, user_id)
    if user is None:
        raise LookupError(f"Usuário não encontrado: {user_id}")

    payload = {
        "recipient": user.email,
        "subject": "Confirme seu e-mail",
        "message": f"Seu token de verificação é: {token}",
    }
    result = _email_adapter.send(payload)
    if not result.get("success"):
        raise RuntimeError(f"Falha ao enviar email de verificação para usuário {user_id}")

    logger.info("verification_email_sent", user_id=str(user_id))


def send_phone_otp(db: Session, *, user_id: UUID, otp: str) -> None:
    """ Envia OTP por SMS para o usuário informado.

    Ignora silenciosamente se o usuário não tiver número de telefone cadastrado.

    Args:
        db: Sessão ativa do banco de dados.
        user_id: UUID do usuário destinatário.
        otp: Código OTP a incluir na mensagem.

    Raises:
        LookupError: Se o usuário não for encontrado.
        RuntimeError: Se o adapter reportar falha no envio.
    """
    user = get_user_by_id(db, user_id)
    if user is None:
        raise LookupError(f"Usuário não encontrado: {user_id}")

    if not user.phone_number:
        logger.warning("verification_sms_skipped", user_id=str(user_id), reason="phone_missing")
        return

    payload = {
        "recipient": user.phone_number,
        "message": f"Seu código de verificação é: {otp}",
    }
    result = _sms_adapter.send(payload)
    if not result.get("success"):
        raise RuntimeError(f"Falha ao enviar SMS de verificação para usuário {user_id}")

    logger.info("verification_sms_sent", user_id=str(user_id))
