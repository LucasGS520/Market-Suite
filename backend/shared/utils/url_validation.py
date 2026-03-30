""" Utilidades simples para normalização e validação básica de URLs

O foco do módulo é oferecer normalização previsível para deduplicação e
validação mínima (esquema e host), sem heurísticas específicas de
marketplace. Isso reduz casos-borda complexos e mantém o fluxo
determinístico para os serviços ``market_alert`` e ``market_scraper``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse, urlunparse
import re


@dataclass(frozen=True)
class UrlIssue:
    """ Representa inconsistências simples identificadas durante a validação """
    code: str
    message: str

_ALLOWED_SCHEMES = {"http", "https"}

def _validate_hostname(host: str | None) -> None:
    """ Confere apenas a existência de host e caracteres básicos """
    if not host or not host.strip():
        raise ValueError("URL inválida ou malformada")

def _ensure_scheme(url: str) -> str:
    """ Garante esquema HTTP/HTTPS e remove fragmentos supérfluos """
    parsed_raw = urlparse(url)
    scheme = (parsed_raw.scheme or "https").lower()

    if parsed_raw.scheme and scheme not in _ALLOWED_SCHEMES:
        #Bloqueamos esquemas não suportados para evitar protocolos inseguros
        raise ValueError("A URL deve utilizar HTTP ou HTTPS")
    
    if parsed_raw.scheme:
        parsed = parsed_raw
    elif parsed_raw.netloc:
        parsed = parsed_raw._replace(scheme="https")
    else:
        parsed = urlparse(f"https://{url}")

    parsed_scheme = (parsed.scheme or "https").lower()
    if parsed_scheme not in _ALLOWED_SCHEMES:
        raise ValueError("A URL deve utilizar HTTP ou HTTPS")
    
    if parsed.username or parsed.password:
        raise ValueError("Credenciais embutidas não são permitidas")

    if not parsed.netloc:
        raise ValueError("URL inválida ou malformada")
    
    _validate_hostname(parsed.hostname)

    sanitized = parsed._replace(scheme=parsed_scheme, fragment="")
    return urlunparse(sanitized)

def normalize_product_url(url: str) -> str:
    """ Remove espaços extras e aplica esquema seguro nas URLs """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL inválida ou malformada")
    
    return _ensure_scheme(raw)

def canonicalize_product_url(url: str) -> str:
    """ Produz uma representação canônica estável para URLs de produto."""

    normalized = normalize_product_url(url)
    parsed = urlparse(normalized)

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    port = parsed.port
    if port in {80, 443}:
        port = None

    netloc = host
    if port:
        netloc = f"{host}:{port}"

    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/") or "/"

    canonical = parsed._replace(
        scheme=(parsed.scheme or "https").lower(),
        netloc=netloc,
        path=path or "/",
        params="",
        query="",
        fragment="",
    )
    return urlunparse(canonical)

def check_url_compatibility(
    url: str,
    *,
    ensure_public_endpoint: Callable[[str], UrlIssue | None] | None = None,
) -> UrlIssue | None:
    """ Validações mínimas para garantir formato seguro e previsível """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if not host:
        return UrlIssue(code="invalid_url", message="URL inválida ou malformada")
    
    if parsed.username or parsed.password:
        return UrlIssue(code="invalid_url", message="Credenciais embutidas não são permitidas")

    try:
        _validate_hostname(host)
    except ValueError:
        return UrlIssue(code="invalid_url", message="URL inválida ou malformada")

    if ensure_public_endpoint:
        issue = ensure_public_endpoint(host)
        if issue:
            return issue
    
    return None

def normalize_and_validate_product_url(url: str) -> tuple[str, UrlIssue | None]:
    """ Normaliza URLs de produto com validação mínima de formato """
    normalized = canonicalize_product_url(url)
    issue = check_url_compatibility(normalized)
    return normalized, issue

def normalize_product_url_for_storage(url: str) -> str:
    """ Normaliza URLs para armazenamento sem heurísticas adicionais """
    raw_value = str(url or "").strip()
    if not raw_value:
        return ""
    
    try:
        return canonicalize_product_url(raw_value)
    except ValueError:
        return ""
    
def normalize_competitor_url(url: str) -> str:
    """ Normaliza URL de concorrente garantindo consistência com o scraping e o CRUD """
    raw_value = str(url or "").strip()
    if not raw_value:
        return ""
    try:
        return canonicalize_product_url(raw_value)
    except ValueError:
        #Mantém fallback seguro para preservar compatibilidade com URLs legadas já persistidas
        return raw_value

__all__ = [
    "UrlIssue",
    "normalize_product_url",
    "normalize_and_validate_product_url",
    "canonicalize_product_url",
    "normalize_product_url_for_storage",
    "normalize_competitor_url",
    "check_url_compatibility",
]
    