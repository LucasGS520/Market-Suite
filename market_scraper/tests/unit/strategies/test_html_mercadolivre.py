""" Testes para extratores específicos do Mercado Livre """

import pytest

from market_scraper.strategies.html_static import MercadoLivreHtmlStaticStrategy


@pytest.fixture
def strategy() -> MercadoLivreHtmlStaticStrategy:
    """ Instância da estratégia do Mercado Livre para os testes """
    return MercadoLivreHtmlStaticStrategy()

@pytest.fixture
def html_meta_sem_jsonld() -> str:
    """ HTML fictício com meta tags, mas sem blocos JSON-LD """
    return (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta ML" />'
        '<meta itemprop="price" content="50.00" />'
        '<meta itemprop="priceCurrency" content="BRL" />'
        "</head></html>"
    )

@pytest.fixture
def html_com_jsonld() -> str:
    """ HTML contendo bloco JSON-LD com dados de produto """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto JSON-LD","offers":{"@type":"Offer","price":"199.90","priceCurrency":"BRL"}}'
        "</script>"
        "</head></html>"
    )

@pytest.fixture
def html_fallback() -> str:
    """ HTML com apenas elementos ``h1`` e classes de preço """
    return (
        "<html><head></head><body>"
        '<h1 class="ui-pdp-title">Produto Fallback</h1>'
        '<span class="andes-money-amount__fraction">1234</span>'
        '<span class="andes-money-amount__cents">56</span>'
        "</body></html>"
    )

@pytest.fixture
def html_fallback_com_moeda() -> str:
    """ HTML de fallback com meta tag de moeda diferente de BRL """
    return (
        "<html><head>"
        '<meta itemprop="priceCurrency" content="USD" />'
        "</head><body>"
        '<h1 class="ui-pdp-title">Produto Dólar</h1>'
        '<span class="andes-money-amount__fraction">123</span>'
        '<span class="andes-money-amount__cents">45</span>'
        "</body></html>"
    )

@pytest.mark.asyncio
async def test_extrai_de_json_ld(strategy: MercadoLivreHtmlStaticStrategy, html_com_jsonld: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Valida extração de nome e preço diretamente de um bloco JSON-LD """
    async def fake_fetch(self, url: str) -> str:
        return html_com_jsonld

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON-LD"
    assert detalhes["current_price"] == "R$ 199,90"

@pytest.mark.asyncio
async def test_extrai_de_meta_tags(strategy: MercadoLivreHtmlStaticStrategy, html_meta_sem_jsonld: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração correta quando apenas meta tags estão disponíveis """
    async def fake_fetch(self, url: str) -> str:
        return html_meta_sem_jsonld

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Meta ML"
    assert detalhes["current_price"] == "R$ 50,00"

@pytest.mark.asyncio
async def test_extrai_de_seletores_fallback(strategy: MercadoLivreHtmlStaticStrategy, html_fallback: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica uso de seletores específicos quando meta tags não existem """
    async def fake_fetch(self, url: str) -> str:
        return html_fallback

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Fallback"
    assert detalhes["current_price"] == "R$ 1.234,56"

@pytest.mark.asyncio
async def test_extrai_moeda_nao_brl_em_fallback(strategy: MercadoLivreHtmlStaticStrategy, html_fallback_com_moeda: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que a moeda informada em meta tag seja preservada no fallback """
    async def fake_fetch(self, url: str) -> str:
        return html_fallback_com_moeda

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Dólar"
    assert detalhes["current_price"] == "USD 123,45"
