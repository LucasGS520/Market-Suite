import pytest

from app.utils.constants import to_mobile_url, MOBILE_DOMAIN


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
