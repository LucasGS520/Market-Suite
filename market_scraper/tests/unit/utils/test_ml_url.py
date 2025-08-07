from alert_app.utils.ml_url import canonicalize_ml_url, is_product_url


def test_canonicalize_extracts_id():
    url = "https://m.mercadolivre.com.br/MLB-1234-celular"
    assert canonicalize_ml_url(url) == "https://produto.mercadolivre.com.br/MLB-1234"

def test_canonicalize_returns_none_when_not_found():
    url = "https://www.example.com/item"
    assert canonicalize_ml_url(url) is None

def test_canonicalize_returns_none_for_external_hosts_with_id():
    url = "https://www.example.com/MLB-9999"
    assert canonicalize_ml_url(url) is None

def test_is_product_url_detection():
    assert is_product_url("https://produto.mercadolivre.com.br/MLB-1")
    assert is_product_url("https://m.mercadolivre.com.br/MLB-1")
    assert not is_product_url("https://lista.mercadolivre.com.br/MLB-1-foo")
