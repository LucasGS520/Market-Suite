""" Geração e manipulação de tokens de verificação e reset. """

import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from market_alert.core.config_alert import settings


def generate_verification_token() -> str:
    """ Gera token único para verificação de contas. """
    #UUID garante baixa colisão entre tokens
    return str(uuid.uuid4())

def generate_reset_token() -> str:
    """ Gera token para processos de redefinição de senha """
    #Mesmo mecanismo utilizado para tokens de verificação
    return str(uuid.uuid4())

def generate_phone_otp() -> str:
    """ Gera um OTP numérico de 6 dígitos para validação de telefone """
    return f"{secrets.randbelow(1_000_000):06d}"

def hash_token(raw_token: str) -> str:
    """ Gera hash para tokens de verificação usando sal do serviço """
    salted = f"{settings.SECRET_KEY}:{raw_token}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()

def token_expiry(minutes=15):
    """ Calcula instante de expiração a partir de ``minutes``. """
    #Usa UTC para evitar problemas de fuso horário
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)
