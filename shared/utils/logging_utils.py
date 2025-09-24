""" Utilitário ajudante para registro estruturado """

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_DEFAULT_PLACEHOLDER = "[REDACTED]"
_SENSITIVE_KEYSWORDS = {
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "senha",
    "secret",
    "cookie",
    "cookies",
    "session",
    "sessid",
    "bearer",
    "jwt",
    "credential",
    "credencial",
}


def mask_identifier(value: str, visible: int = 4) -> str:
    """ Retorna um identificador parcialmente mascarado para privacidade em logs """
    if not value:
        return value
    if len(value) <= visible * 2:
        return value
    return f"{value[:visible]}***{value[-visible:]}"

def _sanitize_url(value: str, placeholder: str) -> str | None:
    """ Remove parâmetros sensíveis de URLs utilizadas em logs estruturados """
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    
    if not parsed.query:
        return None
    
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if not query_items:
        return None
    
    has_sensitive = False
    sanitized_items: list[tuple[str, str]] = []

    for key, val in query_items:
        normalized = key.lower()
        if any(keyword in normalized for keyword in _SENSITIVE_KEYSWORDS):
            sanitized_items.append((key, placeholder))
            has_sensitive = True
        else:
            sanitized_items.append((key, val))

    if not has_sensitive:
        return None

    sanitized_query = urlencode(sanitized_items, doseq=True)
    return urlunparse(parsed._replace(query=sanitized_query))

def _sanitize_string(value: str, placeholder: str) -> str:
    """ Retorna uma string segura para registro em log, mascarando dados sensíveis """
    sanitized_url = _sanitize_url(value, placeholder)
    if sanitized_url is not None:
        return sanitized_url
    
    lowered = value.lower()
    patterns = (
        "token=",
        "token:",
        "authorization=",
        "authorization:",
        "bearer ",
        "cookie=",
        "cookie:",
        "senha=",
        "senha:",
        "password=",
        "password:",
        "secret=",
        "secret:",
        "set-cookie",
        "jwt",
    )
    if any(pattern in lowered for pattern in patterns):
        return placeholder
    
    return value

def sanitize_log_data(data: Any, *, placeholder: str = _DEFAULT_PLACEHOLDER) -> Any:
    """ Sanitiza valores antes do envio aos logs estruturados """
    if isinstance(data, Mapping):
        sanitized: dict[Any, Any] = {}
        for key, value in data.items():
            key_str = str(key).lower()
            if any(keyword in key_str for keyword in _SENSITIVE_KEYSWORDS):
                sanitized[key] = placeholder
            else:
                sanitized[key] = sanitize_log_data(value, placeholder=placeholder)
        return sanitized
    
    if isinstance(data, (list, tuple)):
        sanitized_items = [sanitize_log_data(item, placeholder=placeholder) for item in data]
        return type(data)(sanitized_items)
    
    if isinstance(data, set):
        return {sanitize_log_data(item, placeholder=placeholder) for item in data}
    
    if isinstance(data, str):
        return _sanitize_string(data, placeholder)
    
    return data


__all__ = ["mask_identifier", "sanitize_log_data"]
