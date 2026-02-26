""" Serviços relacionados à autenticação e gerenciamento de tokens """

from uuid import uuid4
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status, Request
from sqlalchemy.orm import Session

from market_alert.core.bruteforce import (
    block_ip,
    reset_failed_attempts,
    record_failed_attempt,
)
from market_alert.core.config_alert import settings
from market_alert.core.jwt import create_access_token
from market_alert.core.tokens import (
    generate_verification_token,
    generate_reset_token,
    token_expiry,
)
from market_alert.models.models_users import User
from market_alert.schemas.schemas_auth import (
    ResetPasswordRequest,
    ResetPasswordConfirmRequest,
    ChangePasswordRequest,
    ChangeEmailRequest,
    EmailTokenRequest,
    TokenPairResponse,
    RefreshRequest,
)
from market_alert.enums.enums_users import UserStatus
from market_alert.users.crud.crud_account import (
    get_user_by_email,
    get_user_by_phone,
    get_user_by_id,
)
from market_alert.auth.crud.crud_refresh_token import (
    create_refresh_token,
    get_refresh_token,
    revoke_refresh_token,
)


logger = structlog.get_logger("service.auth")

def _resolve_refresh_token(
    payload: RefreshRequest | None,
    request: Request,
) -> str | None:
    """ Obtém o refresh token via payload ou cookie HttpOnly, com fallback opcional no payload """
    cookie_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    if payload and payload.refresh_token:
        return payload.refresh_token
    return None

def authenticate_user(
    db: Session,
    identifier: str,
    password: str,
) -> User | None:
    """ Verifica credenciais e retorna o usuário se forem válidas """
    user = get_user_by_email(db, identifier)
    if not user:
        user = get_user_by_phone(db, identifier)
    if user and user.check_password(password):
        return user
    return None

def login_user(
    request: Request,
    db: Session,
    username: str,
    password: str,
) -> TokenPairResponse:
    """ Organiza o fluxo de login: Bloqueio por IP, Autenticação, Registro de falhas ou sucesso, Geração de JWT """
    ip = request.client.host
    email = username

    #Bloqueio de IP antes de autenticar
    block_ip(request)

    user = authenticate_user(db, email, password)
    if not user:
        logger.warning("login_failed", ip=ip, email=email)
        record_failed_attempt(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos", headers={"WWW-Authenticate": "Bearer"})

    if not user.is_active or user.status == UserStatus.suspended:
        logger.warning("login_inactive", ip=ip, email=email)
        record_failed_attempt(request)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário desativado. Contate o administrador")

    #Login bem-sucedido
    reset_failed_attempts(request)
    #Atualiza last_login
    user.last_login = datetime.now(timezone.utc)

    db.commit()

    logger.info("login_success", user_id=str(user.id), ip=ip)

    token = create_access_token(
        {
            "sub": str(user.id),
            "jti": str(uuid4()),
            "email_verified": user.email_verified,
            "phone_verified": user.phone_number_verified,
            "roles": [user.role],
            "status": user.status.value,
        }
    )
    raw_refresh, refresh = create_refresh_token(
        db, str(user.id), request.client.host, request.headers.get("user-agent", "")
    )
    logger.info("refresh_token_issued_on_login", refresh_id=str(refresh.id), user_id=str(user.id))
    return TokenPairResponse(access_token=token, refresh_token=raw_refresh, token_type="bearer")

def send_verification_email_service(
    db: Session,
    current_user: User,
) -> None:
    """ Gera um token de verificação de email sem envio automático """
    token = generate_verification_token()
    current_user.verification_token = token
    db.commit()
    logger.info("verification_token_generated", user_id=str(current_user.id))
    logger.info("verification_dispatch_skipped", user_id=str(current_user.id))

def confirm_email_verification_service(
    db: Session,
    request_model: EmailTokenRequest,
) -> None:
    """ Confirma verificação de email usando token """
    token = request_model.token
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        logger.warning("verification_failed", token=token)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token inválido")

    user.email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    user.verification_token = None
    db.commit()
    logger.info("verification_success", user_id=str(user.id))

def request_password_reset_service(
    db: Session,
    request_model: ResetPasswordRequest,
) -> None:
    """ Inicia o fluxo de reset de senha gerando um token sem envio automático """
    email = request_model.email
    user = get_user_by_email(db, email)
    if not user:
        logger.warning("reset_request_failed", email=email)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    token = generate_reset_token()
    user.reset_token = token
    user.reset_token_expires = token_expiry()
    db.commit()
    logger.info("reset_token_generated", user_id=str(user.id))
    logger.info("reset_dispatch_skipped", user_id=str(user.id))

def confirm_password_service(
    db: Session,
    request_model: ResetPasswordConfirmRequest,
) -> None:
    """ Confirma reset de senha usando token e define nova senha """
    token = request_model.token
    new_password = request_model.new_password
    user = db.query(User).filter(User.reset_token == token).first()

    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.now(timezone.utc):
        logger.warning("reset_confirm_failed", token=token)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token inválido ou expirado")

    user.set_password(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    logger.info("reset_confirm_success", user_id=str(user.id))

def change_password_service(
    db: Session,
    current_user: User,
    request_model: ChangePasswordRequest,
) -> None:
    """ Altera a senha de um usuário autenticado """
    old = request_model.old_password
    new = request_model.new_password

    if not current_user.check_password(old):
        logger.warning("change_password_failed", user_id=str(current_user.id), reason="wrong_old_password")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha antiga incorreta")

    current_user.set_password(new)
    db.commit()
    logger.info("change_password_success", user_id=str(current_user.id))

def change_email_service(
    db: Session,
    current_user: User,
    request_model: ChangeEmailRequest,
) -> None:
    """ Altera o email de um usuário autenticado e marca como não verificado """
    new_email = request_model.new_email
    if get_user_by_email(db, new_email):
        logger.warning("change_email_failed", user_id=str(current_user.id), email=new_email)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este e-mail já está em uso")

    current_user.email = new_email
    current_user.email_verified = False
    current_user.email_verified_at = None
    db.commit()
    logger.info("change_email_success", user_id=str(current_user.id), email=new_email)

# ---------- REFRESH TOKENS ----------
def refresh_token_service(
    db: Session,
    payload: RefreshRequest | None,
    request: Request,
) -> TokenPairResponse:
    """ Troca um Refresh Token válido por um novo Access Token e novo Refresh Token (rotacionando) """
    request_id = request.headers.get("x-request-id") or request.headers.get("x-requestid")
    raw_token = _resolve_refresh_token(payload, request)
    if not raw_token:
        logger.warning("refresh_failed_missing", ip=request.client.host, request_id=request_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autorizado")
    refresh = get_refresh_token(db, raw_token)
    if not refresh:
        logger.warning("refresh_failed_invalid", ip=request.client.host, request_id=request_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autorizado")

    #Revoga o token antigo
    revoke_refresh_token(db, refresh)

    #Cria raw + registro
    new_raw, new_refresh = create_refresh_token(db, str(refresh.user_id), request.client.host, request.headers.get("user-agent", ""))

    #Gera novo access token com jti unico
    user = get_user_by_id(db, refresh.user_id)
    access_token = create_access_token(
        {
            "sub": str(refresh.user_id),
            "jti": str(uuid4()),
            "email_verified": user.email_verified,
            "phone_verified": user.phone_number_verified,
            "roles": [user.role],
            "status": user.status.value,
        }
    )
    logger.info(
        "refresh_success",
        user_id=str(refresh.user_id),
        old_id=str(refresh.id),
        new_token_id=str(new_refresh.id),
        ip=request.client.host,
        request_id=request_id,
    )
    return TokenPairResponse(access_token=access_token, refresh_token=new_raw, token_type="bearer")

def logout_service(
    db: Session,
    payload: RefreshRequest | None,
    request: Request,
) -> None:
    """ Logout de sessão: revoga apenas o Refresh Token fornecido """
    raw_token = _resolve_refresh_token(payload, request)
    if not raw_token:
        logger.warning("logout_missing_token", ip=request.client.host)
        return
    refresh = get_refresh_token(db, raw_token)
    if not refresh:
        logger.warning("logout_invalid_token", ip=request.client.host)
        return

    revoke_refresh_token(db, refresh)
    logger.info("logout_success", token_id=str(refresh.id), user_id=str(refresh.user_id), ip=request.client.host)
