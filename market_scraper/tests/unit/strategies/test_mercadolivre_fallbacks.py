""" Testes adicionais para fallback do Mercado Livre """

import pytest
import sys, types, importlib.machinery, importlib.util

from alembic.util.pyfiles import load_module_py
from celery.bin.result import result

#Importações para simular módulos mínimos necessários
from market_scraper.utils.constants import STEALTH_HEADERS, GENERIC_COOKIES

@pytest.fixture(autouse=True)
def stub_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Configura módulos mínimos de utilidades para o teste e restaura ao final """
    utils_stub = types.ModuleType("market_scraper.utils")
    utils_stub.__path__ = []
    monkeypatch.setattr(sys.modules, "market_scraper.utils", utils_stub)
    monkeypatch.setitem(sys.modules, "market_scraper.utils.constants", types.SimpleNamespace(STEALTH_HEADERS={}, GENERIC_COOKIES={}))
    loader = importlib.machinery.SourceFileLoader(
        "market_scraper.utils.data_quality_validator",
        "market_scraper/utils/data_quality_validator.py",
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    data_quality_validator = importlib.util.module_from_spec(spec)
    loader.exec_module(data_quality_validator)
    monkeypatch.setitem(sys.modules, loader.name, data_quality_validator)

from market_scraper.strategies.html_static import MercadoLivreHtmlStaticStrategy


@pytest.fixture
def strategy() -> MercadoLivreHtmlStaticStrategy:
    """ Instância de estratégia específica do Mercado Livre """
    return MercadoLivreHtmlStaticStrategy()

@pytest.fixture
def html_price_tag() -> str:
    """ HTML que contém apenas seletores ``price-tag`` para preço """
    return (
        "<html><body>"
        '<h1 class="ui-pdp-title">Produto Price Tag</h1>'
        '<span class="price-tag-fraction">999</span>'
        '<span class="price-tag-decimal">99</span>'
        "</body></html>"
    )

@pytest.fixture
def html_itemprop() -> str:
    """ HTML com ``h1`` genérico e ``span[itemprop=`price`]`` """
    return (
        "<html><body>"
        "<h1>Produto Itemprop</h1>"
        '<span itemprop="price" content="987.65"></span>'
        "</body></html>"
    )

@pytest.mark.asyncio
async def test_extrai_com_price_tag(strategy: MercadoLivreHtmlStaticStrategy, html_price_tag: str, monkeypatch:pytest.MonkeyPatch) -> None:
    """ Garante extração correta quando o preço usa ``price-tag`` """
    async def fake_fetch(self, url: str) -> str:
        return html_price_tag

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Price Tag"
    assert detalhes["current_price"] == "R$ 999,99"

@pytest.mark.asyncio
async def test_extrai_de_itemprop_e_h1_generico(strategy: MercadoLivreHtmlStaticStrategy, html_itemprop: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica fallback para ``h1`` genérico e ``span[itemprop=`price`]`` """
    async def fake_fetch(self, url: str) -> str:
        return html_itemprop

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch)
    resultado = await strategy.get_data("http://exemplo.com/produto")
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Itemprop"
    assert detalhes["current_price"] == "R$ 987,65"
