""" Casos de uso de verificação, segurança e identidade de usuário """

from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from market_alert.infraestructure.security.bruteforce import enforce_rate_limit
from market_alert.core.config_alert import settings
from market_alert.core.tokens import generate_phone_otp, generate_verification_token, token_expiry
from market_alert.models.models_users import User
from market_alert.schemas.schemas_users import UserResponse, VerificationResendRequest
from market_alert.enums.enums_users import UserStatus, VerificationKind
from market_alert.users.crud import crud_account, crud_identity
from backend.market_alert.users.tasks.verification_tasks import send_email_verification, send_phone_otp


def verify_email(db: Session, token: str) -> UserResponse:
    """ Valida token de e-mail e ativa a conta quando aplicável """
    verification = crud_identity.consume_verification(
        db,
        kind=VerificationKind.email,
        raw_token=token,
    )
    if not verification:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token inválido ou expirado")
    user = crud_account.get_user_by_id(db, verification.user_id)
    crud_account.set_email_verified(db, user)
    if user.status == UserStatus.pending and (not user.phone_number or user.phone_number_verified):
        crud_account.set_status(db, user, UserStatus.active)
    return user

def verify_phone_otp(db: Session, user_id: UUID, otp: str) -> UserResponse:
    """ Valida OTP de telefone e ativa a conta quando aplicável """
    user = crud_account.get_user_by_id(db, user_id)
    if not user.phone_number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Telefone não cadastrado")
    verification = crud_identity.get_active_by_user(db, user_id, VerificationKind.phone_number)
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
    consumed = crud_identity.consume_verification(
        db,
        kind=VerificationKind.phone_number,
        raw_token=otp,
        user_id=user_id,
    )
    if not consumed:
        crud_identity.increment_attempts(db, verification)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP inválido")
    crud_account.set_phone_verified(db, user)
    if user.status == UserStatus.pending and user.email_verified:
        crud_account.set_status(db, user, UserStatus.active)
    return user

def resend_verification(db: Session, user: User, payload: VerificationResendRequest, request: Request) -> None:
    """ Reenvia token/OTP respeitando limites de tentativa e cooldown """
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
        crud_identity.create_verification(
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
        crud_identity.create_verification(
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
