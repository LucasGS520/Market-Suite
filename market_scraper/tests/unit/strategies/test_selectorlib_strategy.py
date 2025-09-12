import pytest

from market_scraper.strategies.selectorlib_strategy import SelectorLibStrategy


@pytest.fixture
def strategy(monkeypatch) -> SelectorLibStrategy:
    """ Estratégia configurada com HTML fictício para os testes """
    html = "<html><body><h1>Produto Exemplo</h1><span class='price'>R$ 10,00</span></body></html>"

    async def fake_fetch(self, url: str) -> str:
        return html
    
    monkeypatch.setattr(SelectorLibStrategy, "_fetch_html", fake_fetch)
    return SelectorLibStrategy()

@pytest.mark.asyncio
async def test_extrai_dados_com_template(strategy: SelectorLibStrategy) -> None:
    """ Garante extração correta dos campos usando SelectorLib """
    url = "http://example.com/produto"
    assert strategy.supports_url(url)
    resultado = await strategy.get_data(url)
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Exemplo"
    assert detalhes["current_price"] == "R$ 10,00"
    assert detalhes["url"] == url
    