import pytest

from market_scraper.utils.constants import to_mobile_url, MOBILE_DOMAIN
from shared.utils.ml_url import PRODUCT_HOSTS


def test_to_mobile_url_converts_mercadolivre_domain():
    url = "https://www.mercadolivre.com.br/item"
    mobile = to_mobile_url(url)
    assert mobile == f"https://{MOBILE_DOMAIN}/item"

def test_to_mobile_url_keeps_p_path_unchanged():
    url = "https://www.mercadolivre.com.br/p/some-app-link"
    assert to_mobile_url(url) == url

def test_to_mobile_url_keeps_nested_p_path_unchanged():
    url = "https://www.mercadolivre.com.br/produto/p/MLB123"
    assert to_mobile_url(url) == url

def test_product_hosts_contains_mobile_domain():
    assert MOBILE_DOMAIN in PRODUCT_HOSTS
