""" Testes o módulo ``market_scraper.parsers.parsel`` """

from market_scraper.parsers.parsel import parse_with_parsel


def test_parse_with_parsel_json_ld() -> None:
    """ Deve extrair dados do JSON-LD disponível no HTML """
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Console XYZ", "offers": {"price": "2999.00"}}
    </script>
    </head><body></body></html>
    """
    resultado = parse_with_parsel(html, "https://loja.test/console_xyz")
    assert resultado == {
        "name": "Console XYZ",
        "current_price": "2999.00",
        "url": "https://loja.test/console_xyz",
    }

def test_parse_with_parsel_fallback_selectors() -> None:
    """ Deve utilizar seletores CSS e XPath quando JSON-LD não está presente """
    html = """
    <html><head>
    <meta property="og:title" content="Livro" />
    </head><body>
    <span id="price">89.90</span>
    </body></html>
    """
    resultado = parse_with_parsel(html, "https://loja.test/livro")
    assert resultado == {
        "name": "Livro",
        "current_price": "89.90",
        "url": "https://loja.test/livro",
    }
    