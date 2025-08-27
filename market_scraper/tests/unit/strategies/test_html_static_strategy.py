""" Testes unitários para a estratégia de HTML estático """

import pytest
from celery.bin.result import result

from market_scraper.strategies.html_static import HtmlStaticStrategy


@pytest.fixture
def strategy() -> HtmlStaticStrategy:
    """ Instância padrão de estratégia para uso nos testes """
    return HtmlStaticStrategy()


@pytest.fixture
def html_json_ld() -> str:
    """ HTML mínimo contendo bloco JSON-LD de produto """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Produto JSON","offers":{"price":"10.00","priceCurrency":"BRL"}}'
        "</script>" "</head></html>"
    )

@pytest.fixture
def html_meta_tags() -> str:
    """ HTML mínimo com meta tags de preço e título """
    return (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta" />'
        '<meta itemprop="price" content="20.00" />'
        '<meta itemprop="priceCurrency" content="BRL" />'
        "</head></html>"
    )

@pytest.fixture
def html_invalido() -> str:
    """ HTML sem informações necessárias para validação """
    return "<html><head><title>Vazio</title></head></html>"

@pytest.mark.asyncio
async def test_extrai_dados_de_json_ld(strategy: HtmlStaticStrategy, html_json_ld: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica extração de dados quando há JSON-LD válido """
    async def fake_fetch(self, url: str) -> str:
        return html_json_ld

    #Ignora validações rígidas para focar apenas na extração
    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", lambda self, data: None)
    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON"
    assert detalhes["current_price"] == "R$ 10,00"

@pytest.mark.asyncio
async def test_extrai_dados_de_meta_tags(strategy: HtmlStaticStrategy, html_meta_tags: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica extração de dados quando apenas meta tags estão presentes """
    async def fake_fetch(self, url: str) -> str:
        return html_meta_tags

    #Ignora validações rígidas para focar apenas na extração
    monkeypatch.setattr("market_scraper.strategies.html_static.DataQualityValidator.validate", lambda self, data: None)
    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Meta"
    assert detalhes["current_price"] == "R$ 20,00"

@pytest.mark.asyncio
async def test_retorna_erro_quando_html_invalido(strategy: HtmlStaticStrategy, html_invalido: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante retorno de erro quando a validação falha """
    async def fake_fetch(self, url: str) -> str:
        return html_invalido

    monkeypatch.setattr(HtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    assert resultado == {"status": "error"}
