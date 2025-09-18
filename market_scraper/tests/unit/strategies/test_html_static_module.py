""" Testes unitários para o módulo utilitário de parsing HTML estático """

from __future__ import annotations

import pytest

from market_scraper.strategies.html_static import (
    parse_generic_html,
    parse_meli_html,
    parse_amazon_html,
    parse_magalu_html,
)

@pytest.fixture
def empty_structutured_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Força a extração de dados estruturados a retornar vazio durante os testes """
    monkeypatch.setattr("market_scraper.strategies.html_static.extract_structured_data", lambda *_: {"json-ld": [], "microdata": [], "opengraph": []})

def test_parse_generic_html_prioriza_dados_estruturados(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Valida que o parser genérico utiliza JSON-LD quando disponível """
    html = "<html><head></head><body></body></html>"
    dados = {
        "json-ld": [
            {
                "@type": "Product",
                "name": "Produto Estruturado",
                "offers": {"price": "199.90", "priceCurrency": "BRL"},
            }
        ],
        "microdata": [],
        "opengraph": [],
    }
    monkeypatch.setattr("market_scraper.strategies.html_static.extract_structured_data", lambda *_: dados)
    url = "https://exemplo.com/produto"
    resultado = parse_generic_html(html, url)
    assert resultado == {
        "name": "Produto Estruturado",
        "current_price": "R$ 199,90",
        "url": url,
    }

def test_parse_generic_html_fallback_meta_tags(empty_structutured_data: None) -> None:
    """ Garante uso de meta-tags como fallback quando não há dados estruturados """
    html = (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta" />'
        '<meta property="og:price:amount" content="349.99" />'
        '<meta property="og:price:currency" content="USD" />'
        "</head></html>"
    )
    url = "https://exemplo.com/meta"
    resultado = parse_generic_html(html, url)
    assert resultado["name"] == "Produto Meta"
    assert resultado["current_price"] == "USD 349,99"
    assert resultado["url"] == url

def test_parse_generic_html_incompleto(empty_structutured_data: None) -> None:
    """ HTML sem informações deve retornar campos vazios porém com a URL """
    url = "https://exemplo.com/incompleto"
    resultado = parse_generic_html("<html><body></body></html>", url)
    assert resultado == {"name": None, "current_price": "", "url": url}

def test_parse_meli_html_extrai_fracao_e_centavos(empty_structutured_data: None) -> None:
    """Confere extração correta dos elementos específicos do Mercado Livre"""
    html = (
        "<html><head>"
        '<meta itemprop="priceCurrency" content="BRL" />'
        "</head><body>"
        '<h1 class="ui-pdp-title">Notebook Gamer</h1>'
        '<span class="andes-money-amount__fraction">1.299</span>'
        '<span class="andes-money-amount__cents">99</span>'
        "</body></html>"
    )
    url = "https://mercadolivre.com/produto"
    resultado = parse_meli_html(html, url)
    assert resultado["name"] == "Notebook Gamer"
    assert resultado["current_price"] == "R$ 1.299,99"
    assert resultado["url"] == url


def test_parse_meli_html_utiliza_itemprop_price(empty_structured_data: None) -> None:
    """Valida fallback para ``itemprop=price`` mantendo a moeda informada"""
    html = (
        "<html><head>"
        '<meta itemprop="priceCurrency" content="USD" />'
        "</head><body>"
        "<h1>Console Importado</h1>"
        '<span itemprop="price">USD 499,90</span>'
        "</body></html>"
    )
    url = "https://mercadolivre.com/produto/importado"
    resultado = parse_meli_html(html, url)
    assert resultado["name"] == "Console Importado"
    assert resultado["current_price"] == "USD 499,90"


def test_parse_meli_html_retorna_campos_vazios(empty_structured_data: None) -> None:
    """Ausência de título e preço deve resultar em campos vazios"""
    url = "https://mercadolivre.com/produto/vazio"
    resultado = parse_meli_html("<html><body></body></html>", url)
    assert resultado == {"name": None, "current_price": "", "url": url}


def test_parse_amazon_html_extrai_a_offscreen(empty_structured_data: None) -> None:
    """Garante extração de preço exibido no elemento ``a-offscreen``"""
    html = (
        "<html><head>"
        '<meta property="og:price:currency" content="BRL" />'
        "</head><body>"
        '<span id="productTitle">Kindle Paperwhite</span>'
        '<div id="corePriceDisplay_desktop_feature_div"><span class="a-offscreen">R$ 399,00</span></div>'
        "</body></html>"
    )
    url = "https://amazon.com.br/dp/kindle"
    resultado = parse_amazon_html(html, url)
    assert resultado["name"] == "Kindle Paperwhite"
    assert resultado["current_price"] == "R$ 399,00"


def test_parse_amazon_html_compoe_whole_e_fraction(empty_structured_data: None) -> None:
    """Verifica combinação de partes inteiras e decimais quando necessário"""
    html = (
        "<html><body>"
        '<span id="productTitle">Echo Dot</span>'
        '<span class="a-price-whole">279</span>'
        '<span class="a-price-fraction">90</span>'
        '<span class="a-price-symbol">R$</span>'
        "</body></html>"
    )
    url = "https://amazon.com.br/dp/echo"
    resultado = parse_amazon_html(html, url)
    assert resultado["current_price"] == "R$ 279,90"


def test_parse_amazon_html_sem_preco(empty_structured_data: None) -> None:
    """Quando o preço não está presente o campo deve ficar vazio"""
    html = "<html><body><span id=\"productTitle\">Produto Sem Preço</span></body></html>"
    url = "https://amazon.com.br/dp/sem-preco"
    resultado = parse_amazon_html(html, url)
    assert resultado == {"name": "Produto Sem Preço", "current_price": "", "url": url}

def test_parse_magalu_html_usa_initial_state(empty_structured_data: None) -> None:
    """Confirma extração a partir do ``window.__INITIAL_STATE__``"""
    html = "".join(
        [
            "<html><head><script>window.__INITIAL_STATE__ = ",
            "{\"product\": {\"details\": {\"name\": \"Smart TV\", \"price\": 2599.9}}};",
            "</script></head><body></body></html>",
        ]
    )
    url = "https://magalu.com/produto"
    resultado = parse_magalu_html(html, url)
    assert resultado == {"name": "Smart TV", "current_price": "R$ 2.599,90", "url": url}

def test_parse_magalu_html_lida_com_pricevalue(empty_structured_data: None) -> None:
    """Garante leitura do campo ``priceValue`` no estado inicial"""
    html = "".join(
        [
            "<html><head><script>window.__INITIAL_STATE__ = ",
            "{\"details\": {\"title\": \"Ventilador\", \"priceValue\": 189.99}};",
            "</script></head><body></body></html>",
        ]
    )
    url = "https://magalu.com/produto/ventilador"
    resultado = parse_magalu_html(html, url)
    assert resultado == {"name": "Ventilador", "current_price": "R$ 189,99", "url": url}

def test_parse_magalu_html_sem_dados(empty_structured_data: None) -> None:
    """Quando nenhum dado é encontrado os campos devem permanecer vazios"""
    url = "https://magalu.com/produto/vazio"
    resultado = parse_magalu_html("<html><body></body></html>", url)
    assert resultado == {"name": None, "current_price": "", "url": url}