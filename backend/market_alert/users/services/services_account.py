""" Casos de uso de gestão de conta (cadastro, atualização e status) """

from uuid import UUID

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from market_alert.infraestructure.security.bruteforce import enforce_rate_limit
from market_alert.core.config_alert import settings
from market_alert.core.tokens import generate_phone_otp, generate_verification_token, token_expiry
from market_alert.models.models_users import User
from market_alert.schemas.schemas_users import UserCreate, UserResponse, UserUpdate
from market_alert.enums.enums_users import UserStatus, VerificationKind
from market_alert.users.crud import crud_account, crud_identity
from market_alert.users.domain.account_domain import normalize_email, normalize_phone
from backend.market_alert.users.tasks.verification_tasks import send_email_verification, send_phone_otp


logger = structlog.get_logger("users.services.account")


def register_user(db: Session, user_data: UserCreate, request: Request) -> UserResponse:
    """ Registra usuário pendente e inicia fluxo de verificação de identidade """
    ip_address = request.client.host if request.client else "unknown"
    enforce_rate_limit(
        key=f"register:{ip_address}",
        max_attempts=settings.REGISTRATION_MAX_PER_HOUR,
        window_seconds=60 * 60,
        error_message="Muitas tentativas de cadastro, tente novamente mais tarde.",
    )
    normalized_email = normalize_email(user_data.email)
    normalized_phone = normalize_phone(user_data.phone_number)
    payload = user_data.model_copy(
        update={
            "email": normalized_email,
            "phone_number": normalized_phone,
        },
    )
    user = crud_account.create_user(db, payload)

    token = generate_verification_token()
    expires_at = token_expiry(settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
    crud_identity.create_verification(
        db,
        user_id=user.id,
        kind=VerificationKind.email,
        raw_token=token,
        expires_at=expires_at,
        metadata={
            "ip": ip_address,
            "agent": request.headers.get("user-agent")
        },
    )
    send_email_verification.delay(str(user.id), token)

    if payload.phone_number:
        otp = generate_phone_otp()
        crud_identity.create_verification(
            db,
            user_id=user.id,
            kind=VerificationKind.phone_number,
            raw_token=otp,
            expires_at=expires_at,
            attempts_remaining=settings.PHONE_VERIFICATION_MAX_ATTEMPTS,
            metadata={
                "ip": ip_address,
                "agent": request.headers.get("user-agent")
            },
        )
        send_phone_otp.delay(str(user.id), otp)
    return user

def update_user(db: Session, user_id: UUID, updates: UserUpdate) -> UserResponse:
    """ Atualiza campos administrativos permitidos """
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nenhuma alteração informada")
    
    logger.debug("service_update_user", user_id=str(user_id), fields=list(update_data.keys()))
    return crud_account.update_user(db, user_id, updates)

def change_user_status(db: Session, user_id: UUID, active: bool) -> UserResponse:
    """ Altera o status de atividade do usuário garantindo rastreabilidade """
    logger.debug("service_change_user_status", user_id=str(user_id), active=active)
    return crud_account.toggle_user_active(db, user_id, active)

def read_my_profile(current_user: User) -> UserResponse:
    """ Retorna perfil do usuário autenticado sem consultas adicionais """
    return UserResponse.model_validate(current_user)

def validate_phone_number(phone_number: str | None) -> None:
    """  telefone informado no endpoint de gestão de conta """
    normalize_phone(phone_number)
    