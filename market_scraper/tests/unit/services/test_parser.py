"""Testes unitários do módulo de parser de HTML."""

import pytest
from bs4 import BeautifulSoup

from app.services.services_parser import (
    parse_product_details,
    RobustProductParser,
    CaptchaDetectedError
)

def test_parser_returns_all_fields_with_valid_html():
    html = """ 
    <html>
      <head>
        <meta property="og:image" content="https://example.com/thumb.jpg" />
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "name": "Tênis de Corrida",
          "offers": {
            "@type": "Offer",
            "price": "199.99",
            "availability": "https://schema.org/InStock"
          }
        }
        </script>
      </head>
      <body>
        <h1 class="ui-pdp-title">Tênis de Corrida</h1>
        <span class="ui-seller-data-header__title">Vendedor Oficial</span>
        <span class="andes-money-amount__fraction">199</span>
        <span class="andes-money-amount__cents">99</span>
        <p class="ui-pdp-color--GREEN">Frete grátis</p>
      </body>
    </html>
    """

    parser = RobustProductParser()
    result = parse_product_details(html, url="https://produto.mercadolivre.com.br/ABC123")

    #Verifica que parse_product_details utiliza RobustProductParser
    assert result == parser.parse(html, url="https://produto.mercadolivre.com.br/ABC123")

    assert isinstance(result, dict)
    assert result["name"] == "Tênis de Corrida"
    assert result["current_price"] == "R$ 199,99"
    assert result["old_price"] is None or isinstance(result["old_price"], str)
    assert result["shipping"] == "Frete Grátis"
    assert result["seller"] == "Vendedor Oficial"
    assert result["thumbnail"] == "https://example.com/thumb.jpg"

def test_parser_uses_json_ld_price_when_available():
    html = """
    <html>
      <head>
        <meta property="og:image" content="https://example.com/img.jpg" />
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "offers": {
            "@type": "Offer",
            "price": "888.88"
          }
        }
        </script>
      </head>
      <body>
        <h1 class="ui-pdp-title">Smartphone XYZ</h1>
        <span class="ui-seller-data-header__title">Loja X</span>
        <p class="ui-pdp-color--GREEN">Frete grátis</p>
      </body>
    </html>
    """

    parser = RobustProductParser()
    result = parse_product_details(html, url="https://produto.mercadolivre.com.br/XYZ888")

    assert result == parser.parse(html, url="https://produto.mercadolivre.com.br/XYZ888")

    assert result["current_price"] == "R$ 888,88"
    assert result["name"] == "Smartphone XYZ"

def test_parser_raises_captcha_error():
    html = """
    <html>
      <body>
        <p>Digite os caracteres que aparecem na imagem</p>
      </body>
    </html>
    """

    with pytest.raises(CaptchaDetectedError, match="CAPTCHA detectado"):
        parse_product_details(html, url="https://produto.mercadolivre.com.br/ABCAPTCHA")

def test_parser_raises_value_error_on_malformed_html():
    html = "<html><body><p>conteudo invalido</p></body></html>"

    with pytest.raises(ValueError):
        parse_product_details(html, url="https://exemplo.com/produto")

def test_parser_handles_p_page_json():
    html = """
    <html>
      <head>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "title": "Produto P",
              "price": 1550.0,
              "seller": {"nickname": "Loja P"},
              "picture": "https://example.com/img.jpg"
            }
          }
        }
        </script>
      </head>
    </html>
    """

    result = parse_product_details(html, url="https://www.mercadolivre.com.br/produto/p/MLB123")

    assert result["name"] == "Produto P"
    assert result["current_price"] == "R$ 1.550,00"
    assert result["seller"] == "Loja P"
    assert result["thumbnail"] == "https://example.com/img.jpg"

def test_parser_handles_preloaded_state():
    html = """
    <html>
      <head>
        <meta property="og:image" content="https://example.com/img.jpg" />
      </head>
      <body>
        <span class="ui-seller-data-header__title">Loja X</span>
        <script>
        window.__PRELOADED_STATE__ = {
          "title": "Produto JS",
          "price": 2000.0
        };
        </script>
      </body>
    </html>
    """

    result = parse_product_details(html, url="https://www.mercadolivre.com.br/produto/MLB999")

    assert result["name"] == "Produto JS"
    assert result["current_price"] == "R$ 2.000,00"

def test_looks_like_product_page_returns_false_for_search_results():
    html = """
        <html>
      <head>
        <meta property="og:type" content="website" />
      </head>
      <body>
        <div class="ui-search-layout"></div>
      </body>
    </html>
    """

    from app.services.services_parser import looks_like_product_page

    assert looks_like_product_page(html) is False

def test_looks_like_product_page_returns_false_when_og_type_not_product():
    html = """
        <html>
      <head>
        <meta property="og:type" content="website" />
      </head>
      <body>
        <h1 class="ui-pdp-title">Produto X</h1>
      </body>
    </html>
    """

    from app.services.services_parser import looks_like_product_page

    assert looks_like_product_page(html) is False
