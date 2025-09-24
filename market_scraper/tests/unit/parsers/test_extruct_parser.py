""" Testes para o módulo ``market_scraper.parsers.extruct`` """

from market_scraper.parsers.extruct import parse_with_extruct


def test_parse_with_extruct_json_ld() -> None:
    """ Deve extrair nome e preço a partir de JSON-LD válido """
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Câmera", "offers": {"price": "3500.00"}}
    </script>
    </head><body></body></html>
    """
    resultado = parse_with_extruct(html, "https://exemplo.com/produto")
    assert resultado == {
        "name": "Câmera",
        "current_price": "3500.00",
        "url": "https://exemplo.com/produto",
    }

def test_parse_with_extruct_fallback_opengraph() -> None:
    """ Deve utilizar dados do OpenGraph quando JSON-LD não está presente """

    html = """
    <html><head>
    <meta property="og:title" content="Notebook" />
    <meta property="product:price:amount" content="5999.90" />
    </head><body></body></html>
    """
    resultado = parse_with_extruct(html, "https://exemplo.com/notebook")
    assert resultado == {
        "name": "Notebook",
        "current_price": "5999.90",
        "url": "https://exemplo.com/notebook",
    }
