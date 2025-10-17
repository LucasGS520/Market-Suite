""" Testes unitários para validação e normalização de URLs """

from __future__ import annotations

from market_scraper.utils.url_validation import UrlIssue, check_url_compatibility, normalize_product_url


def test_normalize_product_url_adds_scheme() -> None:
    """ Garante que o esquema seja aplicado automaticamente """
    url = normalize_product_url("mercadolivre.com.br/MLB-123")
    assert url.startswith("https://")

def test_normalize_product_url_preserves_host() -> None:
    """ Confere que a normalização não altera o host original """
    url = normalize_product_url("https://www.mercadolivre.com.br/MLB-123")
    assert url.startswith("https://www.mercadolivre.com.br")

def test_check_url_compatibility_unsupported_domain() -> None:
    """ Bloqueia marketplaces não suportados """
    issue = check_url_compatibility("https://loja.inexistente.com/produto")
    assert isinstance(issue, UrlIssue)
    assert issue.code == "unsupported_marketplace"

def test_check_url_compatibility_not_product() -> None:
    """ Rejeita páginas que não representam produtos """
    issue = check_url_compatibility("https://www.amazon.com.br/ofertas")
    assert isinstance(issue, UrlIssue)
    assert issue.code == "not_a_product"

def test_check_url_compatibility_accepts_product_path() -> None:
    """ Aceita um caminho válido de poduto """
    issue = check_url_compatibility("https://www.amazon.com.br/dp/B000000001")
    assert issue is None
