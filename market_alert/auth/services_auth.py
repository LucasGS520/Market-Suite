""" Serviços relacionados à autenticação e gerenciamento de tokens """

import structlog
from types import SimpleNamespace

from uuid import uuid4
from datetime import datetime, timezone
from fastapi import HTTPException, status, Request
from sqlalchemy.orm import Session

from alert_app.crud.crud_refresh_token import create_refresh_token, get_refresh_token, revoke_refresh_token
from alert_app.crud.crud_user import get_user_by_email
from alert_app.core.bruteforce import block_ip, reset_failed_attempts, record_failed_attempt
from alert_app.core.jwt import create_access_token
from alert_app.core.tokens import generate_verification_token, generate_reset_token, token_expiry
from alert_app.notifications.manager import get_notification_manager
from alert_app.crud.crud_notification_logs import has_recent_duplicate_notification
from alert_app.core.config import settings
from alert_app.schemas.schemas_auth import TokenResponse, ResetPasswordRequest, ResetPasswordConfirmRequest, ChangePasswordRequest, ChangeEmailRequest, EmailTokenRequest
from alert_app.schemas.schemas_auth import TokenPairResponse, RefreshRequest
from alert_app.models.models_users import User


logger = structlog.get_logger("service.auth")

def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """ Verifica credenciais e retorna o usuário se forem válidas """
    user = get_user_by_email(db, email)
    if user and user.check_password(password):
        return user
    return None

def login_user(request: Request, db: Session, username: str, password: str) -> TokenResponse:
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

    if not user.is_active:
        logger.warning("login_inactive", ip=ip, email=email)
        record_failed_attempt(request)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário desativado. Contate o administrador")

    #Login bem-sucedido
    reset_failed_attempts(request)
    #Atualiza last_login
    user.last_login = datetime.now(timezone.utc)

    db.commit()

    logger.info("login_success", user_id=str(user.id), ip=ip)

    token = create_access_token({"sub": str(user.id), "jti": str(uuid4())})
    return TokenResponse(access_token=token, token_type="bearer")

def send_verification_email_service(db: Session, current_user: User) -> None:
    """ Gera e envia um token de verificação de email """
    token = generate_verification_token()
    current_user.verification_token = token
    db.commit()
    logger.info("verification_token_generated", user_id=str(current_user.id))

    manager = get_notification_manager()
    subject = "Verifique seu e-mail"
    message = f"Seu token de verificação é: {token}"
    if not has_recent_duplicate_notification(db, current_user.id, subject, message, settings.ALERT_DUPLICATE_WINDOW):
        manager.send(db, current_user, subject, message, alert_rule_id=None)

def confirm_email_verification_service(db: Session, request_model: EmailTokenRequest) -> None:
    """ Confirma verificação de email usando token """
    token = request_model.token
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        logger.warning("verification_failed", token=token)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token inválido")

    user.is_email_verified = True
    user.verification_token = None
    db.commit()
    logger.info("verification_success", user_id=str(user.id))

def request_password_reset_service(db: Session, request_model: ResetPasswordRequest) -> None:
    """ Inicia o fluxo de reset de senha gerando um token e enviando por e-mail """
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

    manager = get_notification_manager()
    dummy_user = SimpleNamespace(email=email, id=user.id)
    subject = "Reset de senha"
    message = f"Use este token para resetar sua senha: {token}"
    if not has_recent_duplicate_notification(db, user.id, subject, message, settings.ALERT_DUPLICATE_WINDOW):
        manager.send(db, dummy_user, subject, message, alert_rule_id=None)

def confirm_password_service(db: Session, request_model: ResetPasswordConfirmRequest) -> None:
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

def change_password_service(db: Session, current_user: User, request_model: ChangePasswordRequest) -> None:
    """ Altera a senha de um usuário autenticado """
    old = request_model.old_password
    new = request_model.new_password

    if not current_user.check_password(old):
        logger.warning("change_password_failed", user_id=str(current_user.id), reason="wrong_old_password")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha antiga incorreta")

    current_user.set_password(new)
    db.commit()
    logger.info("change_password_success", user_id=str(current_user.id))

def change_email_service(db: Session, current_user: User, request_model: ChangeEmailRequest) -> None:
    """ Altera o email de um usuário autenticado e marca como não verificado """
    new_email = request_model.new_email
    if get_user_by_email(db, new_email):
        logger.warning("change_email_failed", user_id=str(current_user.id), email=new_email)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este e-mail já está em uso")

    current_user.email = new_email
    current_user.is_email_verified = False
    db.commit()
    logger.info("change_email_success", user_id=str(current_user.id), email=new_email)

# ---------- REFRESH TOKENS ----------
def refresh_token_service(db: Session, payload: RefreshRequest, request: Request) -> TokenPairResponse:
    """ Troca um Refresh Token válido por um novo Access Token e novo Refresh Token (rotacionando) """
    raw_token = payload.refresh_token
    refresh = get_refresh_token(db, raw_token)
    if not refresh:
        logger.warning("refresh_failed_invalid", token=raw_token, ip=request.client.host)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido ou expirado")

    #Revoga o token antigo
    revoke_refresh_token(db, refresh)

    #Cria raw + registro
    new_raw, new_refresh = create_refresh_token(db, str(refresh.user_id), request.client.host, request.headers.get("user-agent", ""))

    #Gera novo access token com jti unico
    access_token = create_access_token({"sub": str(refresh.user_id), "jti": str(uuid4())})

    logger.info("refresh_success", user_id=str(refresh.user_id), old_id=str(refresh.id), new_token_id=str(new_refresh.id), ip=request.client.host)

    return TokenPairResponse(access_token=access_token, refresh_token=new_raw, token_type="bearer")

def logout_service(db: Session, payload: RefreshRequest, request: Request) -> None:
    """ Logout de sessão: revoga apenas o Refresh Token fornecido """
    raw_token = payload.refresh_token
    refresh = get_refresh_token(db, raw_token)
    if not refresh:
        logger.warning("logout_invalid_token", token=raw_token, ip=request.client.host)
        return

    revoke_refresh_token(db, refresh)
    logger.info("logout_success", token_id=str(refresh.id), user_id=str(refresh.user_id), ip=request.client.host)
