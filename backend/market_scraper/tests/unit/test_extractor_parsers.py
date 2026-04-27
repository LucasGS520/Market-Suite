"""Testes unitários para os extratores individuais da camada de extração.

Cada extrator é testado em isolamento para garantir que:
  - retorna dict com name + current_price em HTML favorável
  - retorna None em HTML sem dados relevantes
  - não levanta exceções em HTML malformado
"""

from __future__ import annotations

import pytest

from market_scraper.extraction.parsers.extruct import parse_with_extruct
from market_scraper.extraction.parsers.parsel import parse_with_parsel
from market_scraper.extraction.parsers.beautifulsoup import parse_with_beautifulsoup
from market_scraper.utils import extract_structured_data as structured_data_module


# ── Fixtures de HTML ───────────────────────────────────────────────────────────

_URL = "https://www.mercadolivre.com.br/produto/MLB-123"

_HTML_JSON_LD_PRODUCT = """
<html>
<head>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Smartphone XYZ 128GB",
    "offers": {
      "@type": "Offer",
      "price": "1299.00",
      "priceCurrency": "BRL"
    }
  }
  </script>
</head>
<body><h1>Smartphone XYZ</h1></body>
</html>
"""

_HTML_OG_META = """
<html>
<head>
  <meta property="og:title" content="Console ABC Pro" />
  <meta property="og:price:amount" content="3499.90" />
  <meta property="og:price:currency" content="BRL" />
</head>
<body></body>
</html>
"""

_HTML_ITEMPROP = """
<html>
<head>
  <meta itemprop="name" content="TV LED 55" />
  <meta itemprop="price" content="2799.00" />
</head>
<body></body>
</html>
"""

_HTML_PARSEL_TITLE = """
<html>
<head>
  <meta property="og:title" content="Notebook Gamer 16GB" />
  <script type="application/ld+json">
  {
    "@type": "Product",
    "name": "Notebook Gamer",
    "offers": {"price": "5999.00"}
  }
  </script>
</head>
<body></body>
</html>
"""

_HTML_EMPTY = "<html><body>Página sem produto</body></html>"
_HTML_MALFORMED = "<html<head><script>não fechado"


# ── parse_with_extruct ────────────────────────────────────────────────────────

def test_extruct_extracts_json_ld_product():
    result = parse_with_extruct(_HTML_JSON_LD_PRODUCT, _URL)
    assert result is not None
    assert result.get("name") is not None
    assert result.get("current_price") is not None


def test_extruct_parser_uses_real_extruct_library(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_extract(html, **kwargs):
        calls.append({"html": html, **kwargs})
        return {
            "json-ld": [
                {
                    "@type": "Product",
                    "name": "Produto Extruct",
                    "offers": {"price": "123.45"},
                }
            ],
            "microdata": [],
            "opengraph": [],
        }

    monkeypatch.setattr(structured_data_module, "_extruct_extract", fake_extract)

    result = parse_with_extruct("<html></html>", _URL)

    assert result is not None
    assert result["name"] == "Produto Extruct"
    assert calls[0]["base_url"] == _URL
    assert calls[0]["syntaxes"] == ["json-ld", "microdata", "opengraph"]


def test_extruct_returns_none_on_empty_html():
    result = parse_with_extruct(_HTML_EMPTY, _URL)
    assert result is None


def test_extruct_does_not_raise_on_malformed_html():
    try:
        parse_with_extruct(_HTML_MALFORMED, _URL)
    except Exception as exc:
        pytest.fail(f"parse_with_extruct levantou {exc!r} em HTML malformado")


# ── parse_with_parsel ─────────────────────────────────────────────────────────

def test_parsel_extracts_product_from_og_and_json_ld():
    result = parse_with_parsel(_HTML_PARSEL_TITLE, _URL)
    assert result is not None
    name = result.get("name") or result.get("title")
    price = result.get("current_price") or result.get("price")
    assert name or price  # ao menos um campo extraído


def test_parsel_returns_none_on_empty_html():
    result = parse_with_parsel(_HTML_EMPTY, _URL)
    assert result is None


def test_parsel_does_not_raise_on_malformed_html():
    try:
        parse_with_parsel(_HTML_MALFORMED, _URL)
    except Exception as exc:
        pytest.fail(f"parse_with_parsel levantou {exc!r} em HTML malformado")


# ── parse_with_beautifulsoup ──────────────────────────────────────────────────

def test_beautifulsoup_extracts_og_title():
    result = parse_with_beautifulsoup(_HTML_OG_META, _URL)
    assert result is not None
    assert result.get("name") == "Console ABC Pro"


def test_beautifulsoup_extracts_itemprop_fields():
    result = parse_with_beautifulsoup(_HTML_ITEMPROP, _URL)
    assert result is not None
    assert result.get("name") is not None


def test_beautifulsoup_returns_none_on_html_without_product():
    result = parse_with_beautifulsoup(_HTML_EMPTY, _URL)
    assert result is None


def test_beautifulsoup_does_not_raise_on_malformed_html():
    try:
        parse_with_beautifulsoup(_HTML_MALFORMED, _URL)
    except Exception as exc:
        pytest.fail(f"parse_with_beautifulsoup levantou {exc!r} em HTML malformado")


# ── Consistência de interface ─────────────────────────────────────────────────

@pytest.mark.parametrize("parser_fn", [parse_with_extruct, parse_with_parsel, parse_with_beautifulsoup])
def test_all_parsers_accept_none_url(parser_fn):
    """Todos os parsers devem aceitar url=None sem levantarem TypeError."""
    try:
        parser_fn(_HTML_EMPTY, None)
    except TypeError as exc:
        pytest.fail(f"{parser_fn.__name__} não aceita url=None: {exc}")
    except Exception:
        pass  # outras exceções são aceitáveis (não é TypeError)


@pytest.mark.parametrize("parser_fn", [parse_with_extruct, parse_with_parsel, parse_with_beautifulsoup])
def test_all_parsers_return_dict_or_none(parser_fn):
    result = parser_fn(_HTML_JSON_LD_PRODUCT, _URL)
    assert result is None or isinstance(result, dict)
