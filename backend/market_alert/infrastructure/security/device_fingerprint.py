""" Fingerprint de dispositivo/origem para auditoria e limitação granular """

import hashlib


def compute_device_fingerprint(ip: str, user_agent: str) -> str:
    """
    Deriva um fingerprint estável a partir de IP e User-Agent.

    Usado para:
    - Auditoria: identifica o mesmo dispositivo em diferentes sessões.
    - Rate limiting: bloqueia dispositivos automatizados que rotacionam contas.

    Retorna os primeiros 16 caracteres do sha256 (64 bits de entropia suficientes
    para fingerprint de auditoria sem expor os valores originais nos logs).
    """
    raw = f"{ip}|{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
