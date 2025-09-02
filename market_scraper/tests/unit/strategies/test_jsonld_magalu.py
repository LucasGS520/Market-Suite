""" Testes básicos para a estratégia Magazine Luiza JSON-LD """

import pytest

from market_scraper.strategies.html_static import MagaluHtmlStaticStrategy


@pytest.fixture
def strategy() -> MagaluHtmlStaticStrategy:
    """ Instância da estratégia do Magalu usada nos testes """
    return MagaluHtmlStaticStrategy()

@pytest.mark.asyncio
async def test_sucesso_json_ld(strategy: MagaluHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """Confere extração de dados quando o JSON-LD está presente """
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto JSON Magalu","offers":{"@type":"Offer","price":"149.90","priceCurrency":"BRL"}}'
        "</script>"
        "</head></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        """ Retorna HTML contendo o bloco JSON-LD esperado """
        return html

    monkeypatch.setattr(MagaluHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("https://magalu.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON Magalu"
    assert detalhes["current_price"] == "R$ 149,90"

@pytest.mark.asyncio
async def test_fallback_initial_state(strategy: MagaluHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Utiliza ``window.__INITIAL_STATE__`` quando não há JSON-LD """
    html = (
        "<html><head>"
        '<script>window.__INITIAL_STATE__ = {"produto": {"info": {"name": "Produto State Magalu", "price": 55.66}}};</script>'
        "</head></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        """ Retorna HTML sem JSON-LD para acionar o fallback """
        return html

    monkeypatch.setattr(MagaluHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("https://magalu.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto State Magalu"
    assert detalhes["current_price"] == "R$ 55,66"
