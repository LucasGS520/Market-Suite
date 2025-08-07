""" Funções auxiliares para lidar com headers HTTP """

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


def parse_retry_after(value: str) -> Optional[int]:
    """ Retorna o valor header Retry-After como segundos

    Suporta segundos inteiros ou data HTTP. Devolve 'None' if parsing fails
    """
    if not value:
        return None

    value = value.strip()
    if value.isdigit():
        return int(value)

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(diff))
    except Exception:
        return None

def extract_hostname(url: str) -> str:
    """ Retorna o hostname de uma URL ou string vazia se inválida """
    from urllib.parse import urlparse

    try:
        return urlparse(str(url)).hostname or ""
    except Exception:
        return ""
