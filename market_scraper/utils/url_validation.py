""" Validações de URLs utilizadas pelo serviço de scraping

Fornece funções auxiliares para garantir que a URL recebida pertence a um
marketplace suportado e representa de fato uma página de produto. Essa
camada evita processamentos desnecessários e gera mensagens de erro mais
claras para o cliente da API
"""

from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Callable, Dict

from market_scraper.services.domain_policy import PIPELINE_POLICIES
from market_scraper.utils.http_utils import extract_hostname
from shared.utils.ml_url import canonicalize_ml_url


#Mapeia domínios para funções de verificação de página de produto
_PRODUCT_CHECKS: Dict[str, Callable[[str], bool]] = {
    "mercadolivre.com.br": lambda url: canonicalize_ml_url(url) is not None,
    "amazon.com.br": lambda url: "/dp/" in urlparse(url).path or "/gp/product" in urlparse(url).path,
    "magazineluiza.com.br": lambda url: "/p/" in urlparse(url).path,
}

def _is_supported_marketplace(host: str) -> bool:
    """ Verifica se o host pertence a algum domínio configurado """
    for domain in PIPELINE_POLICIES.keys():
        if domain == "default":
            continue
        if host == domain or host.endswith("." + domain):
            return True
    return False

def _is_product_page(url: str) -> bool:
    """ Confere se a URL parece apontar para uma página de produto """
    host = extract_hostname(url)
    for domain, checker in _PRODUCT_CHECKS.items():
        if host == domain or host.endswith("." + domain):
            return checker(url)
    return False

def check_url_compatibility(url: str) -> str | None:
    """ Valida se a URL é aceita pelo sistema

    Retorna ``None`` quando a URL é valida ou uma mensagem
    explicando o motivo da incompatibilidade
    """
    host = extract_hostname(url)
    if not host:
        return "URL inválida"
    if not _is_supported_marketplace(host):
        return "Marketplace ainda não suportado"
    if not _is_product_page(url):
        return "A URL informada não corresponde a um produto"
    return None
