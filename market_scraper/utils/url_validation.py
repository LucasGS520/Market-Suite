""" Normalização e verificação de URLs aceitas pelo scraper """

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Callable, Dict
from urllib.parse import urlparse, urlunparse

from market_scraper.utils.http_utils import (
    HostResolutionError,
    extract_hostname,
    resolve_public_addresses as http_resolve_public_addresses,
)
from shared.utils.ml_url import canonicalize_ml_url


@dataclass(frozen=True)
class UrlIssue:
    """ Representa um problema encontrado durante a validação da URL """
    code: str
    message: str

SUPPORTED_DOMAINS = {
    "mercadolivre.com.br",
    "amazon.com.br",
    "magazineluiza.com.br",
}

_PRODUCT_CHECKS: Dict[str, Callable[[str], bool]] = {
    "mercadolivre.com.br": lambda url: canonicalize_ml_url(url) is not None,
    "amazon.com.br": lambda url: "/dp/" in urlparse(url).path or "/gp/product" in urlparse(url).path,
    "magazineluiza.com.br": lambda url: "/p/" in urlparse(url).path,
}

def _ensure_scheme(url: str) -> str:
    """ Garante que a URL possua esquema; assume HTTPS por padrão """
    parsed = urlparse(url, scheme="https")
    if not parsed.netloc:
        parsed = urlparse(f"https://{url}")
    if not parsed.netloc:
        raise ValueError("URL inválida ou malformada")
    cleaned = parsed._replace(fragment="")
    return urlunparse(cleaned)

def normalize_product_url(url: str) -> str:
    """ Normaliza a URL removendo fragmentos, aplicando HTTPS e canônicos """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL inválida ou malformada")
    
    normalized = _ensure_scheme(raw)
    host = extract_hostname(normalized)
    if host.endswith("mercadolivre.com.br"):
        canonical = canonicalize_ml_url(normalized)
        if canonical:
            return canonical
    return normalized

def _matches_domain(host: str, domain: str) -> bool:
    """ Retorna ``True`` quando o host pertence ao domínio informado """
    return host == domain or host.endswith(f".{domain}")

def _is_supported_marketplace(host: str) -> bool:
    """ Verifica se o host pertence a uma marketplace suportada """
    return any(_matches_domain(host, domain) for domain in SUPPORTED_DOMAINS)

def _is_product_page(url: str) -> bool:
    """ Confere se a URL parece apontar para uma página de produto """
    host = extract_hostname(url)
    for domain, checker in _PRODUCT_CHECKS.items():
        if _matches_domain(host, domain):
            return checker(url)
    return False

def check_url_compatibility(url: str) -> UrlIssue | None:
    """ Valida a URL normalizada e retorna o primeiro problema encontrado """
    host = extract_hostname(url)
    if not host:
        return UrlIssue(code="invalid_url", message="URL inválida ou malformada")
    
    if not _is_supported_marketplace(host):
        return UrlIssue(code="unsupported_marketplace", message="Marketplace ainda não suportado")
    
    public_issue = _ensure_public_endpoint(host)
    if public_issue:
        return public_issue
    
    if not _is_product_page(url):
        return UrlIssue(code="not_a_product", message="A URL informada não corresponde a um produto")
    return None

def resolve_public_addresses(host: str) -> list[str]:
    """ Mantém o alias padronizado para uso em testes e chamadas legadas """
    #Delegamos para o utilitário compartilhado para preservar a regra única de validação
    return http_resolve_public_addresses(host)

def _ensure_public_endpoint(host: str) -> UrlIssue | None:
    """ Confere se o host aponta para endereços públicos válidos """
    try:
        ip_obj = ip_address(host)
    except ValueError:
        try:
            resolve_public_addresses(host)
        except HostResolutionError as exc:
            return UrlIssue(code="blocked_host", message=str(exc))
        return None
    
    if not ip_obj.is_global:
        return UrlIssue(code="blocked_host", message="Endereços privados não são permitidos")
    
    return None

__all__ = [
    "UrlIssue",
    "normalize_product_url",
    "check_url_compatibility",
    "resolve_public_addresses",
]
