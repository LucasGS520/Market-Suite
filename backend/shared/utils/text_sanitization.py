""" Funções de sanitização para dados coletados do scarping

As rotinas aqui removem caracteres potencialmente perigosos de textos e
normalizam URLs antes de persistir dados vindos do HTML. O objetivo é
prevenir injeções simples sem distorcer o conteúdo exibido ao usuário final.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse


#Caracteres de controle que não devem ser persistidos
_CTRL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
#Remoção simples de marcas HTML para evitar scripts embutidos
_TAG_PATTERN = re.compile(r"<[^>]+>")

def sanitize_text(value: Any | None) -> str | None:
    """ Limpa campos textuais removendo tags HTML e controles """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    no_ctrl = _CTRL_PATTERN.sub("", text)
    sanitized = _TAG_PATTERN.sub("", no_ctrl)
    return sanitized or None

def sanitize_media_url(value: Any | None) -> str | None:
    """ Normaliza URLs de mídia aceitando apenas HTTP ou HTTPS """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    
    return urlunparse(parsed._replace(fragment=""))

__all__ = [
    "sanitize_text",
    "sanitize_media_url",
]
