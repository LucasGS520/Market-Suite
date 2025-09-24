""" Testes para o módulo ``market_scraper.parsers.beautifulsoup`` """

from market_scraper.parsers.beautifulsoup import parse_with_beautifulsoup


def test_parse_with_beautifulosoup_meta_tags() -> None:
    """ Deve extrair nome e preço a partir de metatags """
    html = """
    <html><head>
    <meta property="og:title" content="Smartphone" />
    <meta itemprop="price" content="1999.90" />
    </head><body></body></html>
    """
    resultado = parse_with_beautifulsoup(html, "https://loja.test/smartphone")
    assert resultado == {
        "name": "Smartphone",
        "current_price": "1999.90",
        "url": "https://loja.test/smartphone",
    }

def test_parse_with_beautifulsoup_span_price() -> None:
    """ Deve identificar preço em elementos genéricos """
    html = """
    <html><head><title>Headset</title></head>
    <body><span class="price">R$ 499,90</span></body></html>
    """
    resultado = parse_with_beautifulsoup(html, "https://loja.test/headset")
    assert resultado == {
        "name": "Headset",
        "current_price": "R$ 499,90",
        "url": "https://loja.test/headset",
    }
    