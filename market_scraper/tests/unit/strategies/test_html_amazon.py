""" Testes para extratores específicos da Amazon """

import pytest
from celery.bin.result import result

from market_scraper.strategies.html_static import AmazonHtmlStaticStrategy


@pytest.fixture
def strategy() -> AmazonHtmlStaticStrategy:
    """ Instância da estratégia da Amazon para os testes """
    return AmazonHtmlStaticStrategy()

@pytest.fixture
def html_com_jsonld() -> str:
    """ HTML fictício com bloco JSON-LD de produto """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto JSON-LD Amazon","offers":{"@type":"Offer","price":"99.90","priceCurrency":"BRL"}}'
        "</script>"
        "</head></html>"
    )

@pytest.fixture
def html_meta_tags() -> str:
    """ HTML contendo apenas meta tags com dados de produto """
    return (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta Amazon" />'
        '<meta property="og:price:amount" content="89.99" />'
        '<meta property="og:price:currency" content="USD" />'
        '<meta property="product:price:amount" content="89.99" />'
        '<meta property="product:price:currency" content="USD" />'
        "</head></html>"
    )

@pytest.fixture
def html_fallback() -> str:
    """ HTML com elementos de fallback para título e preço """
    return (
        "<html><body>"
        '<span id="productTitle">Produto Fallback Amazon</span>'
        '<span id="priceblock_ourprice">R$ 1.234,56</span>'
        "</body></html>"
    )

@pytest.mark.asyncio
async def test_extrai_de_json_ld(strategy: AmazonHtmlStaticStrategy, html_com_jsonld: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Valida extração de nome e preço a partir de bloco JSON-LD """
    async def fake_fetch(self, url: str) -> str:
        return html_com_jsonld

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON-LD Amazon"
    assert detalhes["current_price"] == "R$ 99,90"

@pytest.mark.asyncio
async def test_extrai_de_meta_tags(strategy: AmazonHtmlStaticStrategy, html_meta_tags: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração correta quando apenas meta tags estão presentes """
    async def fake_fetch(self, url: str) -> str:
        return html_meta_tags

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Meta Amazon"
    assert detalhes["current_price"] == "USD 89,99"

@pytest.mark.asyncio
async def test_extrai_de_fallback(strategy: AmazonHtmlStaticStrategy, html_fallback: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ verifica uso dos seletores de fallback da Amazon """
    async def fake_fetch(self, url: str) -> str:
        return html_fallback

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Fallback Amazon"
    assert detalhes["current_price"] == "R$ 1.234,56"
