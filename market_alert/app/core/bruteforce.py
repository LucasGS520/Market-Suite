""" Mecanismos de proteção contra ataques de força bruta """

import structlog
from fastapi import HTTPException, Request, status

from app.core.config import settings
from utils.redis_client import get_redis_client


logger = structlog.get_logger("core.bruteforce")

#Cliente Redis compartilhado usado para rastrear tentativas
redis_client = get_redis_client()

def block_ip(request: Request) -> None:
    """ Dependência que bloqueia o IP após exceder tentativas de login """
    #IP do solicitante
    ip = request.client.host
    #Chave utilizada para armazenar as tentativas
    key = f"bf:{ip}"
    try:
        #Recupera o contador de falhas para este IP
        attempts = int(redis_client.get(key) or 0)
    except Exception as e:
        logger.error("redis_unavailable_in_block_ip", error=str(e), ip=ip)
        #Em caso de falha no Redis, não bloqueia por segurança
        return

    if attempts >= settings.BRUTE_FORCE_MAX_ATTEMPTS:
        logger.warning("ip_blocked", ip=ip, attempts=attempts)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de login. Tente novamente mais tarde."
        )

def record_failed_attempt(request: Request) -> None:
    """ Registra uma tentativa de login falhada para IP do cliente """
    #IP do solicitante
    ip = request.client.host
    #Chave no Redis para esse IP
    key = f"bf:{ip}"
    try:
        attempts = redis_client.incr(key)
        if attempts == 1:
            #Define expiração apenas na primeira falha e evita armazenamento eterno de tentativas
            redis_client.expire(key, settings.BRUTE_FORCE_BLOCK_DURATION)
        logger.info("failed_login_attempt", ip=ip, attempts=attempts)
    except Exception as e:
        #Erro de comunicação com Redis impede a contagem
        logger.error("redis_unavailable_in_record_failed", error=str(e), ip=ip)

def reset_failed_attempts(request: Request) -> None:
    """ Limpa o contador de falhas de login para um IP após autenticação bem-sucedida """
    #IP do solicitante
    ip = request.client.host
    #Chave de rastreamento no Redis
    key = f"bf:{ip}"
    try:
        redis_client.delete(key)
        logger.info("reset_failed_attempts", ip=ip)
    except Exception as e:
        #Falha de comunicação torna a limpeza impossível
        logger.error("redis_unavailable_in_reset", error=str(e), ip=ip)
