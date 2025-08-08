""" Dependências e utilidades de segurança e autenticação. """

import structlog
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from alert_app.core.jwt import verify_access_token
from infra.db import get_db
from alert_app.models.models_users import User


logger = structlog.get_logger("core.security")

#Extrai token do cabeçalho Authorization: Bearer <token>
oauth2_scheme = HTTPBearer(bearerFormat="JWT")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """ Dependência que extrai e valida JWT, busca e retorna o User ativo no banco """
    #Token extraído do cabeçalho Authorization
    token = credentials.credentials
    try:
        payload = verify_access_token(token)
        #Campo sub armazena o ID do usuário
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: sub ausente",
                headers={"WWW-Authenticate": "Bearer"}
            )
        user_uuid = UUID(user_id_str)
    except HTTPException:
        #JWT expirado ou inválido, lança HTTPException adequado
        raise
    except Exception as e:
        logger.error("invalid_token_format", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: sub ausente",
            headers={"WWW-Authenticate": "Bearer"}
        )

    #Busca o usuário no banco
    user = db.get(User, user_uuid)
    if not user:
        logger.warning("user_not_found", user_id=user_uuid)
        #Bloqueia login de contas desativadas
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    if not user.is_active:
        logger.warning("user_inactive", user_id=user_uuid)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    return user

def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """ Dependência que so permite acesso se o usuário tiver role == 'admin' """
    if current_user.role != "admin":
        logger.warning("admin_access_denied", user_id=str(current_user.id))
        #Usuários comuns não podem acessar rotas de administrador
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão negada: apenas administradores"
        )
    return current_user
