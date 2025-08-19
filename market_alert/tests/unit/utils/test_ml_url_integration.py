from shared.utils.ml_url import canonicalize_ml_url, is_product_url

def test_canonicalize_return_url_canonical():
    url = "https://m.mercadolivre.com.br/MLB-5555-123"
    esperado = "https://produto.mercadolivre.com.br/MLB-5555"
    assert canonicalize_ml_url(url) == esperado

def test_is_product_url_identified_hosts_invalid():
    url_valida = "https://www.mercadolivre.com.br/MLB-1"
    url_invalida = "https://www.exemplo.com/MLB-1"
    assert is_product_url(url_valida)
    assert not is_product_url(url_invalida)
