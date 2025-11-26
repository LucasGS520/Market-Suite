""" Geração e manipulação de tokens de verificação e reset. """

import uuid
from datetime import datetime, timedelta, timezone


def generate_verification_token() -> str:
    """ Gera token único para verificação de contas. """
    #UUID garante baixa colisão entre tokens
    return str(uuid.uuid4())

def generate_reset_token() -> str:
    """ Gera token para processos de redefinição de senha """
    #Mesmo mecanismo utilizado para tokens de verificação
    return str(uuid.uuid4())

def token_expiry(minutes=15):
    """ Calcula instante de expiração a partir de ``minutes``. """
    #Usa UTC para evitar problemas de fuso horário
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)
