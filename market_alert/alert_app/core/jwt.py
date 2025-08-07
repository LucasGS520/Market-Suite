""" Funções auxiliares para criação e validação de JWTs. """

import structlog
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from fastapi import HTTPException, status

from app.core.config import settings


logger = structlog.get_logger("core.jwt")

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """ Cria token JWT com payload e tempo de expiração. """
    #Copia o payload para evitar mutações
    to_encode = data.copy()
    #Calcula a data de expiração usando o delta informado ou o padrão do settings
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    #O campo ``exp`` é exigido pelo padrão JWT para indicar validade
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    #Registra o evento para auditoria
    logger.info("jwt_created", sub=data.get("sub"), exp=expire.isoformat())
    return token

def verify_access_token(token: str) -> dict:
    """ Decodifica o token JWT e retorna o payload se ele for válido. """
    try:
        #Decodifica o token usando a chave secreta e o algoritmo configurado
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        #Registro para auditoria do token verificado
        logger.debug("jwt_verified", payload=payload)
        return payload
    except ExpiredSignatureError:
        logger.warning("jwt_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        #Qualquer erro de decodificação diferente de expiração indica token inválido
        logger.error("jwt_invalid", error=str(e))
        #Retorna 403 para tokens corrompidos ou assinados com chave incorreta
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"}
        )
