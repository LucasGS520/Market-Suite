""" Testes essenciais dos parsers e extração estruturada do scraper """

from __future__ import annotations

from market_scraper.parsers.html_static import parse_generic_html
from market_scraper.utils.extract_structured_data import extract_structured_data


def test_extract_structured_data_com_json_ld_e_og() -> None:
    """ Garante que JSON-LD e OpenGraph são detectados no HTML de exemplo """
    html = """
    <html>
        <head>
            <script type="application/ld+json">
            {"@type": "Product", "name": "Produto X"}
            </script>
            <meta property="og:title" content="Produto X" />
        </head>
        <body></body>
    </html>
    """

    resultado = extract_structured_data(html, "https://exemplo.com/produto")

    assert resultado["json-ld"]
    assert resultado["json-ld"][0]["name"] == "Produto X"
    assert resultado["opengraph"][0]["og:title"] == "Produto X"


def test_parse_generic_html_retorna_nome_preco_url() -> None:
    """ Valida o parser HTML genérico com um exemplo mínimo """
    html = """
    <html>
        <head>
            <meta property="og:title" content="Produto Teste" />
            <meta itemprop="price" content="199.90" />
            <meta itemprop="priceCurrency" content="BRL" />
        </head>
        <body></body>
    </html>
    """

    resultado = parse_generic_html(html, "https://exemplo.com/produto")

    assert resultado is not None
    assert resultado["name"] == "Produto Teste"
    assert resultado["current_price"] == "R$ 199,90"
    assert resultado["url"] == "https://exemplo.com/produto"
    