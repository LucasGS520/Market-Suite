""" Serviços de entrega de mensagens para verificação de identidade """

from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from market_alert.users.crud import account_crud
from market_alert.notifications.infra.channels.email_adapter import EmailAdapter
from market_alert.notifications.infra.channels.sms_adapter import SmsAdapter


logger = structlog.get_logger("users.services.delivery")

_email_adapter = EmailAdapter()
_sms_adapter = SmsAdapter()

def send_email_verification_message(
    db: Session,
    *,
    user_id: UUID,
    token: str,
) -> None:
    """ Envia mensagem de verificação por e-mail ao usuário informado """
    user = account_crud.get_user_by_id(db, user_id)
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

def send_phone_otp_message(
    db: Session,
    *,
    user_id: UUID,
    otp: str,
) -> None:
    """ Envia OTP por SMS, ignorando usuário sem telefone """
    user = account_crud.get_user_by_id(db, user_id)
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
    