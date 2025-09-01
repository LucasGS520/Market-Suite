""" Testes básicos para a estratégia da Amazon JSON-LD """

import pytest
from celery.bin.result import result

from market_scraper.strategies.html_static import AmazonHtmlStaticStrategy


@pytest.fixture
def strategy() -> AmazonHtmlStaticStrategy:
    """ Instância da estratégia da Amazon para uso nos testes """
    return AmazonHtmlStaticStrategy()

@pytest.mark.asyncio
async def test_sucesso_json_ld(strategy: AmazonHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confere extração quando há bloco JSON-LD válido """
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto JSON Amazon","offers":{"@type":"Offer","price":"99.90","priceCurrency":"BRL"}}'
        "</script>"
        "</head></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        """ Retorna o HTML preparado com JSON-LD """
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("https://amazon.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON Amazon"
    assert detalhes["current_price"] == "R$ 99,90"

@pytest.mark.asyncio
async def test_fallback_sem_json_ld(strategy: AmazonHtmlStaticStrategy, monkeypatch:pytest.MonkeyPatch) -> None:
    """ Extrai dados a partir de seletores quando JSON-LD não existe """
    html = (
        "<html><body>"
        '<span id="productTitle">Produto Fallback Amazon</span>'
        '<span id="priceblock_ourprice">R$ 1.234,56</span>'
        "</body></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        """ Retorna HTML simples sem JSON-LD para testar o fallback """
        return html

    monkeypatch.setattr(AmazonHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("https://amazon.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Fallback Amazon"
    assert detalhes["current_price"] == "R$ 1.234,56"
