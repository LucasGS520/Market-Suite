""" Teste básicos para a estratégia Mercado Livre JSON-LD """

import pytest

from market_alert.utils.comparator import detect_listing_status
from market_scraper.strategies.html_static import MercadoLivreHtmlStaticStrategy


@pytest.fixture
def strategy() -> MercadoLivreHtmlStaticStrategy:
    """ Instância da estratégia do Mercado Livre para uso nos testes """
    return MercadoLivreHtmlStaticStrategy()

@pytest.mark.asyncio
async def test_sucesso_com_json_ld(strategy: MercadoLivreHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante extração correta quando há bloco JSON-LD válido """
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Produto JSON","offers":{"@type":"Offer","price":"199.90","priceCurrency":"BRL"}}'
        "</script>"
        "</head></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        """ Simula o donwload de HTMl retornando o conteúdo estático acima """
        return html

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("https://ml.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto JSON"
    assert detalhes["current_price"] == "R$ 199,90"

@pytest.mark.asyncio
async def test_fallback_sem_json_ld(strategy: MercadoLivreHtmlStaticStrategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Utiliza seletores específicos quando o JSON-LD está ausente """
    html = (
        "<html><body>"
        '<h1 class="ui-pdp-title">Produto Fallback</h1>'
        '<span class="andes-money-amount__fraction">1234</span>'
        '<span class="andes-money-amount__cents">56</span>'
        "</body></html>"
    )

    async def fake_fetch(self, url: str) -> str:
        """ Retorna HTML sem JSON-LD para acionar o fallback """
        return html

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("https://ml.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Fallback"
    assert detalhes["current_price"] == "R$ 1.234,56"
