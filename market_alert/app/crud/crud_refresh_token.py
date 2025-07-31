""" Operações de CRUD para gerenciamento de Refresh Tokens """

import hashlib
import secrets
import structlog

from typing import Optional, List
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models_refresh_token import RefreshToken


logger = structlog.get_logger("crud.refresh_tokens")

def create_refresh_token(db: Session, user_id: str, ip: str, user_agent: str) -> tuple[str, RefreshToken]:
    """ Gera e salva um novo Refresh Token para o usuário """
    #Gera o token hasheado
    raw_token = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    #Cria instância e salva
    refresh = RefreshToken(user_id=user_id, hashed_token=hashed, ip_address=ip, user_agent=user_agent, expires_at=expires)
    db.add(refresh)
    db.commit()
    db.refresh(refresh)

    logger.info("refresh_token_created", token_id=str(refresh.id), user_id=user_id, ip=ip, user_agent=user_agent, expires_at=refresh.expires_at.isoformat())
    return raw_token, refresh

def get_refresh_token(db: Session, raw_token: str) -> Optional[RefreshToken]:
    """ Recupera um Refresh Token a partir do valor informado """
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    refresh = (
        db.query(RefreshToken)
        .filter(RefreshToken.hashed_token == hashed)
        .filter(RefreshToken.revoked.is_(False))
        .first()
    )

    if not refresh:
        logger.warning("refresh_not_found_or_revoked", raw_token=raw_token)
        return None
    if refresh.is_expired():
        logger.warning("refresh_invalid", token_id=str(refresh.id))
        return None
    return refresh

def revoke_refresh_token(db: Session, refresh: RefreshToken) -> None:
    """ Marca um Refresh Token específico como revogado """
    if refresh.revoked:
        logger.debug("refresh_already_revoked", token_id=str(refresh.id))
        return

    refresh.revoked = True
    db.commit()
    logger.info("refresh_token_revoked", token_id=str(refresh.id), user_id=str(refresh.user_id))

def delete_user_refresh_tokens(db: Session, user_id: str) -> int:
    """ Revoga todos os Refresh Tokens de um usuário (logout global) """
    tokens: List[RefreshToken] = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False)
    ).all()

    count = 0
    for token in tokens:
        token.revoked = True
        count += 1

    if count > 0:
        db.commit()
    logger.info("user_refresh_tokens_revoked", user_id=user_id, count=count)
    return count
