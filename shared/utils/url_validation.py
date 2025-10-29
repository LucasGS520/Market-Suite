""" Normalização e validação básica de URLs compartilhadas """

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Callable, Dict
from urllib.parse import ParseResult, urlparse, urlunparse
import re


@dataclass(frozen=True)
class UrlIssue:
    """ Representa inconsistências de URL compartilhadas entre serviços """
    code: str
    message: str

SUPPORTED_DOMAINS = {
    "mercadolivre.com.br",
    "mercadolivre.com"
    "amazon.com.br",
    "amazon.com",
    "magazineluiza.com.br",
    "magazineluiza.com",
}

_ML_PRODUCT_RE = re.compile(r"/MLB[-_]?[0-9]+", re.IGNORECASE)
_AMAZON_PATH_RE = re.compile(r"/(dp|gp/product)/", re.IGNORECASE)
_MAGALU_PATH_RE = re.compile(r"/p/", re.IGNORECASE)

_ALLOWED_SCHEMES = {"http", "https"}

_PRODUCT_CHECKS: Dict[str, Callable[[ParseResult], bool]] = {
    "mercadolivre.com.br": lambda parsed: bool(_ML_PRODUCT_RE.search(parsed.path)),
    "mercadolivre.com": lambda parsed: bool(_ML_PRODUCT_RE.search(parsed.path)),
    "amazon.com.br": lambda parsed: bool(_AMAZON_PATH_RE.search(parsed.path)),
    "amazon.com": lambda parsed: bool(_AMAZON_PATH_RE.search(parsed.path)),
    "magazineluiza.com.br": lambda parsed: bool(_MAGALU_PATH_RE.search(parsed.path)),
    "magazineluiza.com": lambda parsed: bool(_MAGALU_PATH_RE.search(parsed.path)),
}


def _ensure_scheme(url: str) -> str:
    """ Normaliza esquema HTTP/HTTPS mantendo consistência """
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
    
    if not parsed.netloc:
        raise ValueError("URL inválida ou malformada")

    sanitized = parsed._replace(scheme=parsed_scheme, fragment="")
    return urlunparse(sanitized)

def normalize_product_url(url: str) -> str:
    """ Remove espaços extras e aplica esquema seguro nas URLs """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL inválida ou malformada")
    
    return _ensure_scheme(raw)

def _matches_domain(host: str, domain: str) -> bool:
    """ Indica se o host informado pertence ao domínio esperado """
    return host == domain or host.endswith(f".{domain}")

def _is_supported_marketplace(host: str) -> bool:
    """ Confere se o host faz parte dos marketplaces suportados """
    return any(_matches_domain(host, domain) for domain in SUPPORTED_DOMAINS)

def _is_product_page(url: str) -> bool:
    """ Verifica se a URL possui padrões de página de produto """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    for domain, check in _PRODUCT_CHECKS.items():
        if _matches_domain(host, domain):
            return check(parsed)
    return False

def _default_public_endpoint_check(host: str) -> UrlIssue | None:
    """ Bloqueia literais de IP privados sem depender de DNS """
    try:
        ip_obj = ip_address(host)
    except ValueError:
        return None
    
    if not ip_obj.is_global:
        return UrlIssue(code="blocked_host", message="Endereços privados não são permitidos")
    return None

def check_url_compatibility(
    url: str,
    *,
    ensure_public_endpoint: Callable[[str], UrlIssue | None] | None = None,
) -> UrlIssue | None:
    """ Aplica validações de domínio e formato compartilhado """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if not host:
        return UrlIssue(code="invalid_url", message="URL inválida ou malformada")
    
    if not _is_supported_marketplace(host):
        return UrlIssue(code="unsupported_marketplace", message="Marketplace ainda não suportado")
    
    checker = ensure_public_endpoint or _default_public_endpoint_check
    issue = checker(host)
    if issue:
        return issue
    
    if not _is_product_page(url):
        return UrlIssue(code="not_a_product_page", message="A URL informada não corresponde a um produto")
    
    return None

__all__ = [
    "UrlIssue",
    "normalize_product_url",
    "check_url_compatibility",
    "SUPPORTED_DOMAINS",
]
    