""" Testa parsers estáticos e de dados estruturados do scraper """

from __future__ import annotations

from market_scraper.parsers import (
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
        "source": "",
    }
    