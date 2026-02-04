""" Serviços de gerenciamento de usuários centralizando regras de negócio. """

from uuid import UUID

import phonenumbers
import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings
from market_alert.core.tokens import generate_verification_token, generate_phone_otp, token_expiry
from market_alert.core.bruteforce import enforce_rate_limit
from market_alert.crud import crud_user
from market_alert.crud import crud_verification
from market_alert.enums.enums_users import UserStatus, VerificationKind
from market_alert.schemas.schemas_users import UserCreate, UserResponse, UserUpdate, VerificationResendRequest
from market_alert.models.models_users import User
from market_alert.tasks.verification_tasks import send_email_verification, send_phone_otp


logger = structlog.get_logger("service.user")

def _normalize_email(value: str) -> str:
    """ Normaliza email garantindo letras minúsculas """
    return value.strip().lower()

def _normalize_phone(value: str | None) -> str | None:
    """ Normaliza telefone para o formato E.164 """
    if not value:
        return None
    try:
        parsed = phonenumbers.parse(value, "BR")
    except phonenumbers.NumberParseException:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Telefone inválido")
    if not phonenumbers.is_valid_number(parsed):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Telefone inválido")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

def register_user(db: Session, user_data: UserCreate, request: Request) -> UserResponse:
    """ Cria um usuário pendente e dispara verificações de email/telefone """
    ip_address = request.client.host if request.client else "unknown"
    enforce_rate_limit(
        key=f"register:{ip_address}",
        max_attempts=settings.REGISTRATION_MAX_PER_HOUR,
        window_seconds=60 * 60,
        error_message="Muitas tentativas de cadastro, tente novamente mais tarde.",
    )
    normalized_email = _normalize_email(user_data.email)
    normalized_phone = _normalize_phone(user_data.phone_number)
    payload = user_data.model_copy(update={"email": normalized_email, "phone_number": normalized_phone})
    logger.debug("service_register_user", email=payload.email, phone=payload.phone_number)
    user = crud_user.create_user(db, payload)
    token = generate_verification_token()
    expires_at = token_expiry(settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
    crud_verification.create_verification(
        db,
        user_id=user.id,
        kind=VerificationKind.email,
        raw_token=token,
        expires_at=expires_at,
        metadata={"ip": ip_address, "agent": request.headers.get("user-agent")},
    )
    send_email_verification.delay(str(user.id), token)
    if payload.phone_number:
        otp = generate_phone_otp()
        phone_expires = token_expiry(settings.PHONE_VERIFICATION_EXPIRE_MINUTES)
        crud_verification.create_verification(
            db,
            user_id=user.id,
            kind=VerificationKind.phone_number,
            raw_token=otp,
            expires_at=phone_expires,
            attempts_remaining=settings.PHONE_VERIFICATION_MAX_ATTEMPTS,
            metadata={"ip": ip_address, "agent": request.headers.get("user-agent")},
        )
        send_phone_otp.delay(str(user.id), otp)
    return user

def verify_email(db: Session, token: str) -> UserResponse:
    """ Valida o token de email e ativa a conta quando apropriado """
    verification = crud_verification.consume_verification(
        db,
        kind=VerificationKind.email,
        raw_token=token,
    )
    if not verification:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token inválido ou expirado")
    user = crud_user.get_user_by_id(db, verification.user_id)
    crud_user.set_email_verified(db, user)
    if user.status == UserStatus.pending and (not user.phone_number or user.phone_number_verified):
        crud_user.set_status(db, user, UserStatus.active)
    return user

def verify_phone_otp(db: Session, user_id: UUID, otp: str) -> UserResponse:
    """ Valida o OTP de telefone e ativa a conta quando possível """
    user = crud_user.get_user_by_id(db, user_id)
    if not user.phone_number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Telefone não cadastrado")
    verification = crud_verification.get_active_by_user(db, user_id, VerificationKind.phone_number)
    if not verification:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP inválido ou expirado")
    enforce_rate_limit(
        key=f"otp:{user_id}",
        max_attempts=settings.PHONE_VERIFICATION_MAX_ATTEMPTS,
        window_seconds=settings.PHONE_VERIFICATION_MAX_ATTEMPTS * 60,
        error_message="Muitas tentativas inválidas, tente novamente mais tarde.",
    )
    if verification.attempts_remaining is not None and verification.attempts_remaining <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Limite de tentativas atingido")
    consumed = crud_verification.consume_verification(
        db,
        kind=VerificationKind.phone_number,
        raw_token=otp,
        user_id=user_id,
    )
    if not consumed:
        crud_verification.increment_attempts(db, verification)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP inválido")
    crud_user.set_phone_verified(db, user)
    if user.status == UserStatus.pending and user.email_verified:
        crud_user.set_status(db, user, UserStatus.active)
    return user

def resend_verification(db: Session, user: User, payload: VerificationResendRequest, request: Request) -> None:
    """ Reenvia token de verificação respeitando limites de tentativa """
    ip_address = request.client.host if request.client else "unknown"
    enforce_rate_limit(
        key=f"verify:resend:{user.id}:{payload.channel}",
        max_attempts=settings.VERIFICATION_RESEND_MAX_PER_HOUR,
        window_seconds=60 * 60,
        error_message="Limite de reenvios atingido, tente novamente mais tarde.",
    )
    enforce_rate_limit(
        key=f"verify:resend:cooldown:{user.id}:{payload.channel}",
        max_attempts=1,
        window_seconds=settings.VERIFICATION_RESEND_INTERVAL_SECONDS,
        error_message="Aguarde antes de solicitar novo envio.",
    )
    if payload.channel == "email":
        token = generate_verification_token()
        expires_at = token_expiry(settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
        crud_verification.create_verification(
            db,
            user_id=user.id,
            kind=VerificationKind.email,
            raw_token=token,
            expires_at=expires_at,
            metadata={"ip": ip_address, "agent": request.headers.get("user-agent")},
        )
        send_email_verification.delay(str(user.id), token)
        return
    if payload.channel == "phone_number":
        if not user.phone_number:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Telefone não cadastrado")
        otp = generate_phone_otp()
        expires_at = token_expiry(settings.PHONE_VERIFICATION_EXPIRE_MINUTES)
        crud_verification.create_verification(
            db,
            user_id=user.id,
            kind=VerificationKind.phone_number,
            raw_token=otp,
            expires_at=expires_at,
            attempts_remaining=settings.PHONE_VERIFICATION_MAX_ATTEMPTS,
            metadata={"ip": ip_address, "agent": request.headers.get("user-agent")},
        )
        send_phone_otp.delay(str(user.id), otp)
        return
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Canal inválido")

def update_user(db: Session, user_id: UUID, updates: UserUpdate) -> UserResponse:
    """ Atualiza campos permitidos do usuário e evita operações sem alterações """
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nenhuma alteração informada")

    logger.debug("service_update_user", user_id=str(user_id), fields=list(update_data.keys()))
    return crud_user.update_user(db, user_id, updates)


def change_user_status(db: Session, user_id: UUID, active: bool) -> UserResponse:
    """ Altera o status de atividade do usuário garantindo rastreabilidade """
    logger.debug("service_change_user_status", user_id=str(user_id), active=active)
    return crud_user.toggle_user_active(db, user_id, active)
