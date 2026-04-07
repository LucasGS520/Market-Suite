""" Mecanismos de proteção contra ataques de força bruta """

import structlog
from fastapi import HTTPException, Request, status

from shared.utils.redis_client import get_redis_operational

from market_alert.core.config_alert import settings
from market_alert.infrastructure.security.client_identity import resolve_client_ip


logger = structlog.get_logger("infraestructure.security.bruteforce")

#Cliente Redis operacional usado para rastrear tentativas de brute-force
redis_client = get_redis_operational()

def _login_key(ip: str, identifier: str) -> str:
    """ Chave por (IP, conta) — evita colisão entre usuários distintos no mesmo proxy """
    return f"rate:auth:login:{ip}:{identifier}"

def _account_key(identifier: str) -> str:
    """ Chave por conta — agrega tentativas de todos os IPs (defesa contra brute-force distribuído) """
    return f"rate:auth:account:{identifier}"

def block_ip(request: Request, identifier: str = "") -> None:
    """
    Verifica limites de segurança antes de autenticar.
    Aplica duas políticas independentes:
    - (IP, conta): bloqueia um IP específico atacando uma conta específica.
    - conta global: bloqueia uma conta sob ataque distribuído (muitas IPs).
    """
    ip = resolve_client_ip(request)
    try:
        ip_attempts = int(redis_client.get(_login_key(ip, identifier)) or 0)
        if ip_attempts >= settings.BRUTE_FORCE_MAX_ATTEMPTS:
            logger.warning("ip_account_blocked", ip=ip, identifier=identifier, attempts=ip_attempts)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas de login. Tente novamente mais tarde."
            )

        if identifier:
            account_attempts = int(redis_client.get(_account_key(identifier)) or 0)
            if account_attempts >= settings.ACCOUNT_LOCKOUT_MAX_ATTEMPTS:
                logger.warning("account_locked", identifier=identifier, attempts=account_attempts)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Conta temporariamente bloqueada. Tente novamente mais tarde."
                )
    except HTTPException:
        raise
    except Exception:
        logger.exception("redis_unavailable_in_block_ip", ip=ip)
        #Em caso de falha no Redis, não bloqueia por segurança

def record_failed_attempt(request: Request, identifier: str = "") -> None:
    """
    Registra falha de login nos dois contadores independentes:
    - (IP, conta): TTL curto, isola o par atacante/alvo.
    - conta global: TTL longo, detecta ataques distribuídos.
    """
    ip = resolve_client_ip(request)
    try:
        ip_key = _login_key(ip, identifier)
        ip_attempts = redis_client.incr(ip_key)
        if ip_attempts == 1:
            redis_client.expire(ip_key, settings.BRUTE_FORCE_BLOCK_DURATION)

        account_attempts = None
        if identifier:
            acc_key = _account_key(identifier)
            account_attempts = redis_client.incr(acc_key)
            if account_attempts == 1:
                redis_client.expire(acc_key, settings.ACCOUNT_LOCKOUT_DURATION)

        logger.info(
            "failed_login_attempt",
            ip=ip,
            identifier=identifier,
            ip_attempts=ip_attempts,
            account_attempts=account_attempts,
        )
    except Exception:
        logger.exception("redis_unavailable_in_record_failed", ip=ip)

def reset_failed_attempts(request: Request, identifier: str = "") -> None:
    """ Remove ambos os contadores após autenticação bem-sucedida """
    ip = resolve_client_ip(request)
    try:
        redis_client.delete(_login_key(ip, identifier))
        if identifier:
            redis_client.delete(_account_key(identifier))
        logger.info("reset_failed_attempts", ip=ip, identifier=identifier)
    except Exception:
        logger.exception("redis_unavailable_in_reset", ip=ip)

def enforce_rate_limit(
    *,
    key: str,
    max_attempts: int,
    window_seconds: int,
    error_message: str,
) -> None:
    """ Aplica limite de requisições usando contadores Redis """
    try:
        attempts = redis_client.incr(key)
        if attempts == 1:
            redis_client.expire(key, window_seconds)
        if attempts > max_attempts:
            logger.warning("rate_limit_exceeded", key=key, attempts=attempts)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_message,
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("redis_unavailable_in_rate_limit", key=key)
