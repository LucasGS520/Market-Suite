""" Sanitização defensiva de mensagens de exceção para logs e DLQ.

Este módulo reduz risco de vazamento de dados sensíveis quando mensagens
de erro vindas de bibliotecas externas carregam e-mails, tokens, cookies
ou blocos grandes sem valor operacional.
"""

from __future__ import annotations

import re


_DEFAULT_PLACEHOLDER = "[REDACTED]"
_EMAIL_PATTERN = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_JWT_PATTERN = re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b")
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[a-z0-9._\-+/=]+")
_TOKEN_PAIR_PATTERN = re.compile(
    r"(?i)(token|access_token|refresh_token|authorization|cookie|senha|password|secret)=([^\s&;]+)"
)


def sanitize_exception_message(
    value: str | None,
    *,
    max_length: int = 500,
    placeholder: str = _DEFAULT_PLACEHOLDER,
) -> str | None:
    """ Retorna versão segura da mensagem de exceção para persistência.

    A sanitização preserva contexto operacional mínimo e remove os padrões
    mais comuns de segredo. No final, limita o tamanho para evitar registros
    gigantes na tabela de auditoria.
    """
    if value is None:
        return None

    sanitized = _EMAIL_PATTERN.sub(placeholder, value)
    sanitized = _JWT_PATTERN.sub(placeholder, sanitized)
    sanitized = _BEARER_PATTERN.sub(rf"\1{placeholder}", sanitized)
    sanitized = _TOKEN_PAIR_PATTERN.sub(rf"\1={placeholder}", sanitized)

    #Evita armazenar blobs muito grandes que não ajudam na triagem operacional.
    if len(sanitized) > max_length:
        return f"{sanitized[:max_length]}...[TRUNCATED]"
    return sanitized


__all__ = ["sanitize_exception_message"]
