""" Testes para extratores específicos do Mercado Livre """

import pytest

import sys, types, importlib.machinery, importlib.util

from market_scraper.utils.constants import STEALTH_HEADERS, GENERIC_COOKIES

#Stubs de utilidades para isolar dependências pesadas durante os testes
utils_stub = types.ModuleType("market_scraper.utils")
sys.modules["market_scraper.utils"] = utils_stub
sys.modules["market_scraper.utils.constants"] = types.SimpleNamespace(STEALTH_HEADERS={}, GENERIC_COOKIES={})
loader = importlib.machinery.SourceFileLoader(
    "market_scraper.utils.data_quality_validator",
    "market_scraper/utils/data_quality_validator.py",
)
spec = importlib.util.spec_from_loader(loader.name, loader)
data_quality_validator = importlib.util.module_from_spec(spec)
loader.exec_module(data_quality_validator)
sys.modules[loader.name] = data_quality_validator

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
def html_fallback() -> str:
    """ HTML com apenas elementos ``h1`` e classes de preço """
    return (
        "<html><head></head><body>"
        '<h1 class="ui-pdp-title">Produto Fallback</h1>'
        '<span class="andes-money-amount__fraction">1234</span>'
        '<span class="andes-money-amount__cents">56</span>'
        "</body></html>"
    )

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
