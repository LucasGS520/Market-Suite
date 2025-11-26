""" Testa parsers estáticos e de dados estruturados do scraper """

from __future__ import annotations

from market_scraper.parsers import (
    parse_amazon_html,
    parse_magalu_html,
    parse_meli_html,
    parse_generic_html,
    parse_with_beautifulsoup,
    parse_with_extruct,
    parse_with_parsel,
)


def test_parse_generic_html_returns_payload() -> None:
    html = """
    <html>
        <head>
            <meta property="og:title" content="Produto" />
            <meta itemprop="price" content="123.45" />
        </head>
    </html>
    """
    result = parse_generic_html(html, "https://exemplo.com/item")
    assert result == {
        "name": "Produto",
        "current_price": "R$ 123,45",
        "url": "https://exemplo.com/item",
        "source": "generic_html",
    }

def test_parse_generic_html_returns_none_when_missing() -> None:
    html = "<html><body><p>sem preço</p></body></html>"
    assert parse_generic_html(html, "https://exemplo.com/item") is None

def test_parse_with_extruct_handles_json_ld() -> None:
    html = """
    <html>
        <head>
            <script type="application/ld+json">
                {"@type": "Product", "name": "Console", "offers": {"price": "2999.00"}}
            </script>
        </head>
    </html>
    """
    result = parse_with_extruct(html, "https://exemplo.com/console")
    assert result == {
        "name": "Console",
        "current_price": "2999.00",
        "url": "https://exemplo.com/console",
        "source": "structured_data",
    }

def test_parse_with_beautifulsoup_extracts_meta_tags() -> None:
    html = """
    <html>
        <head>
            <meta property="og:title" content="Livro" />
            <meta property="product:price:amount" content="59.90" />
        </head>
    </html>
    """
    result = parse_with_beautifulsoup(html, "https://exemplo.com/livro")
    assert result == {
        "name": "Livro",
        "current_price": "59.90",
        "url": "https://exemplo.com/livro",
        "source": "html_metadata",
    }

def test_parse_with_beautifulsoup_cleans_currency_symbols() -> None:
    html = """
    <html>
        <body>
            <h1>Console</h1>
            <span class="price">R$ 5.999,90</span>
        </body>
    </html>
    """
    result = parse_with_beautifulsoup(html, "https://exemplo.com/console")
    assert result == {
        "name": "Console",
        "current_price": "5.999,90",
        "url": "https://exemplo.com/console",
        "source": "html_metadata",
    }

def test_parse_with_parsel_uses_selectors() -> None:
    html = """
    <html>
        <head>
            <meta property="og:title" content="Tablet" />
            <meta itemprop="price" content="1999.90" />
        </head>
    </html>
    """
    result = parse_with_parsel(html, "https://exemplo.com/tablet")
    assert result == {
        "name": "Tablet",
        "current_price": "1999.90",
        "url": "https://exemplo.com/tablet",
        "source": "parsel",
    }

def test_parse_with_parsel_combines_price_parts() -> None:
    html = """
    <html>
        <head>
            <meta name="twitter:title" content="Console" />
        </head>
        <body>
            <span data-testid="price-integer">3.499</span>
            <span data-testid="price-decimal">90</span>
        </body>
    </html>
    """
    result = parse_with_parsel(html, "https://exemplo.com/console")
    assert result == {
        "name": "Console",
        "current_price": "3499.90",
        "url": "https://exemplo.com/console",
        "source": "parsel",
    }


def test_parse_with_beautifulsoup_handles_twitter_title_and_buybox() -> None:
    html = """
    <html>
        <head>
            <meta name="twitter:title" content="Smartphone" />
        </head>
        <body>
            <span id="price_inside_buybox">R$ 129,90</span>
        </body>
    </html>
    """
    result = parse_with_beautifulsoup(html, "https://exemplo.com/smartphone")
    assert result == {
        "name": "Smartphone",
        "current_price": "129,90",
        "url": "https://exemplo.com/smartphone",
        "source": "html_metadata",
    }


def test_parse_meli_html_handles_test_id_selectors() -> None:
    html = """
    <html>
        <body>
            <h1 data-testid="product-title">Notebook Gamer</h1>
            <span data-testid="price-integer">3.499</span>
            <span data-testid="price-decimal">99</span>
            <span data-testid="price-currency">R$</span>
        </body>
    </html>
    """
    result = parse_meli_html(html, "https://www.mercadolivre.com.br/produto")
    assert result == {
        "name": "Notebook Gamer",
        "current_price": "R$ 3.499,99",
        "url": "https://www.mercadolivre.com.br/produto",
        "source": "generic_html",
    }


def test_parse_amazon_html_reads_buybox_price() -> None:
    html = """
    <html>
        <head>
            <meta name="twitter:title" content="Liquidificador" />
            <meta property="og:price:currency" content="BRL" />
        </head>
        <body>
            <span id="productTitle">Liquidificador Potente</span>
            <span id="price_inside_buybox">R$ 199,90</span>
            <span class="a-price-symbol">R$</span>
        </body>
    </html>
    """
    result = parse_amazon_html(html, "https://www.amazon.com.br/dp/123")
    assert result == {
        "name": "Liquidificador Potente",
        "current_price": "R$ 199,90",
        "url": "https://www.amazon.com.br/dp/123",
        "source": "generic_html",
    }


def test_parse_magalu_html_uses_data_testid_value() -> None:
    html = """
    <html>
        <head>
            <meta property="og:title" content="Televisor" />
        </head>
        <body>
            <span data-testid="price-value">R$ 2.599,00</span>
            <span data-testid="price-currency">R$</span>
        </body>
    </html>
    """
    result = parse_magalu_html(html, "https://www.magazineluiza.com.br/produto")
    assert result == {
        "name": "Televisor",
        "current_price": "R$ 2.599,00",
        "url": "https://www.magazineluiza.com.br/produto",
        "source": "generic_html",
    }
    