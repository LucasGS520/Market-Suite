from __future__ import annotations

from market_scraper.utils.url_validation import UrlIssue, check_url_compatibility, normalize_product_url


def test_normalize_product_url_adds_scheme() -> None:
    url = normalize_product_url("mercadolivre.com.br/MLB-123")
    assert url.startswith("https://")

def test_check_url_compatibility_unsupported_domain() -> None:
    issue = check_url_compatibility("https://loja.inexistente.com/produto")
    assert isinstance(issue, UrlIssue)
    assert issue.code == "unsupported_marketplace"

def test_check_url_compatibility_not_product() -> None:
    issue = check_url_compatibility("https://www.amazon.com.br/ofertas")
    assert isinstance(issue, UrlIssue)
    assert issue.code == "not_a_product"
