""" Normalização e verificação de URLs aceitas pelo scraper """

from __future__ import annotations

from ipaddress import ip_address

from market_scraper.utils.http_utils import (
    HostResolutionError,
    resolve_public_addresses as http_resolve_public_addresses,
)
from shared.utils.url_validation import (
    UrlIssue,
    check_url_compatibility as shared_check_url_compatibility,
    normalize_product_url as shared_normalize_product_url,
)


def check_url_compatibility(url: str) -> UrlIssue | None:
    """ Aplica validações compartilhadas adicionando checagem SSRF """
    shared_issue = shared_check_url_compatibility(
        url,
        _ensure_public_endpoint=_ensure_public_endpoint,
    )
    if shared_issue:
        return shared_issue

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

def normalize_product_url(url: str) -> str:
    """ Normaliza a URL removendo espaços extras e garantindo o esquema """
    return shared_normalize_product_url(url)


__all__ = [
    "UrlIssue",
    "normalize_product_url",
    "check_url_compatibility",
    "resolve_public_addresses",
]
