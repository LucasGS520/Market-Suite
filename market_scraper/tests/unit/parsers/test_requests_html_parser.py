""" Testes para o módulo ``market_scraper.parsers.requests_html`` """

from market_scraper.parsers.requests_html import parse_with_requests_html


def test_parse_with_requests_html() -> None:
    """ Deve retornar campos padronizados utilizando Requests-HTML """
    html = """
    <html><head><title>Monitor UltraWide</title></head>
    <body><span id="price">2599.00</span></body></html>
    """
    resultado = parse_with_requests_html(html, "https://loja.test/monitor")
    assert resultado == {
        "name": "Monitor UltraWide",
        "current_price": "2599.00",
        "url": "https://loja.test/monitor",
    }
    