""" Testes para a estratégia estática do Magazine Luiza """

import pytest

from market_scraper.strategies.html_static import MagaluHtmlStaticStrategy


@pytest.fixture
def strategy() -> MagaluHtmlStaticStrategy:
    """ Instância da estratégia do Magalu para os testes """
    return MagaluHtmlStaticStrategy()

@pytest.fixture
def html_com_jsonld() -> str:
    """ HTML fictício contendo bloco JSON-LD válido """
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto JSON-LD Magalu","offers":{"@type":"Offer","price":"199.90","priceCurrency":"BRL"}}'
        "</script>"
        "</head></html>"
    )

@pytest.fixture
def html_meta_tags() -> str:
    """ HTML com meta-tags utilizando ``og:price:amount`` em real """
    return (
        "<html><head>"
        '<meta property="og:title" content="Produto Meta Magalu" />'
        '<meta property="og:price:amount" content="123.45" />'
        '<meta property="og:price:currency" content="BRL" />'
        "</head></html>"
    )

@pytest.fixture
def html_initial_state() -> str:
    """ HTML contendo ``window.__INITIAL_STATE__`` com dados de produto """
    return (
        "<html><head>"
        '<script>window.__INITIAL_STATE__ = {"produto": {"info": {"name": "Produto State Magalu", "price": 55.66}}};</script>'
        "</head></html>"
    )

@pytest.fixture
def html_initial_state_pricevalue() -> str:
    """ HTML contendo ``window.__INITIAL_STATE__`` com campo ``priceValue`` """
    return (
        "<html><head>"
        '<script>window.__INITIAL_STATE__ = {"produto": {"info": {"title": "Produto PriceValue Magalu", "priceValue": 77.88}}};</script>'
        "</head></html>"
    )

@pytest.fixture
def html_jsonld_invalido_state() -> str:
    """ HTML com JSON-LD inválido e fallback via ``window.__INITIAL_STATE__`` """
    return (
        "<html><head>"
        '<script type="application/ld+json">{invalido</script>'
        '<script>window.__INITIAL_STATE__ = {"produto": {"info": {"name": "Produto Fallback Magalu", "price": 88.99}}};</script>'
        "</head></html>"
    )

@pytest.mark.asyncio
async def test_extrai_de_json_ld(strategy: MagaluHtmlStaticStrategy, html_com_jsonld: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Valida extração de nome e preço a partir de bloco JSON-LD """
    async def fake_fetch(self, url: str) -> str:
        return html_com_jsonld

    monkeypatch.setattr(MagaluHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON-LD Magalu"
    assert detalhes["current_price"] == "R$ 199,90"

@pytest.mark.asyncio
async def test_extrai_de_meta_tags(strategy: MagaluHtmlStaticStrategy, html_meta_tags: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração correta a partir de meta-tags ``og:price:amount`` """
    async def fake_fetch(self, url: str) -> str:
        return html_meta_tags

    monkeypatch.setattr(MagaluHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Meta Magalu"
    assert detalhes["current_price"] == "R$ 123,45"

@pytest.mark.asyncio
async def test_extrai_de_estado_embutido(strategy: MagaluHtmlStaticStrategy, html_initial_state: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Utiliza o ``window.__INITIAL_STATE__`` quando outras fontes falham """
    async def fake_fetch(self, url: str) -> str:
        return html_initial_state

    monkeypatch.setattr(MagaluHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto State Magalu"
    assert detalhes["current_price"] == "R$ 55,66"

@pytest.mark.asyncio
async def test_extrai_pricevalue_de_estado_embutido(strategy: MagaluHtmlStaticStrategy, html_initial_state_pricevalue: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração de ``priceValue`` do ``window.__INITIAL_STATE__`` """
    async def fake_fetch(self, url: str) -> str:
        return html_initial_state_pricevalue

    monkeypatch.setattr(MagaluHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto PriceValue Magalu"
    assert detalhes["current_price"] == "R$ 77,88"

@pytest.mark.asyncio
async def test_fallback_jsonld_invalido(strategy: MagaluHtmlStaticStrategy, html_jsonld_invalido_state: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Aciona o fallback quando o JSON-LD está inválido """
    async def fake_fetch(self, url: str) -> str:
        return html_jsonld_invalido_state

    monkeypatch.setattr(MagaluHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Fallback Magalu"
    assert detalhes["current_price"] == "R$ 88,99"

@pytest.mark.asyncio
async def test_falha_validacao(strategy: MagaluHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Retorna status de erro quando os dados essenciais estão ausentes """
    async def fake_fetch(self, url: str) -> str:
        return "<html></html>"

    monkeypatch.setattr(MagaluHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    assert resultado == {"status": "error"}
