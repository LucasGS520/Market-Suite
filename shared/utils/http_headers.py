""" Utilitários para tratamento de cabeçalhos HTTP """

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping

import structlog


_logger = structlog.get_logger(__name__)

def normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """ Retorna cópia com chaves em minúsculas para evitar duplicidades """
    return {str(key).lower(): value for key, value in headers.items()}

def parse_http_datetime(value: str | None) -> datetime | None:
    """ Converte valores de cabeçalhos HTTP em ``datetime`` UTC quando possível """
    if not value: 
        return None
    
    candidate = value.strip()
    if not candidate:
        return None
    
    try:
        parsed = parsedate_to_datetime(candidate)
    except (TypeError, ValueError):
        _logger.warning("invalid_http_datetime", header_value=candidate)
        return None
    
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


__all__ = [
    "normalize_headers",
    "parse_http_datetime",
]
