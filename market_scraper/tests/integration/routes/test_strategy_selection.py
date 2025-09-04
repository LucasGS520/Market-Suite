from __future__ import annotations

""" Testes de seleção dinâmica de estratégias de scraping """

from typing import Any

from fastapi.testclient import TestClient
import pytest

from market_scraper.main import app
from market_scraper.strategies.base import ScrapingStrategy
from market_scraper.services import domain_policy
from market_scraper.services import services_scraper_common as common
from market_scraper.strategies.html_static import MercadoLivreHtmlStaticStrategy, AmazonHtmlStaticStrategy, ShopeeHtmlStaticStrategy, MagaluHtmlStaticStrategy


def _preparar_ambiente(monkeypatch) -> None:
    """ Configura dependências para evitar operações externas nos testes """
    #Desabilita uso real de cache
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)

    #Evita chamadas HTTP das estratégias HTML
    async def fake_html_get_data(self, **k):
        return {
            "status": "success",
            "details": {"name": "Fake", "current_price": "R$ 10,00"},
        }

    for cls in [
        MercadoLivreHtmlStaticStrategy,
        AmazonHtmlStaticStrategy,
        ShopeeHtmlStaticStrategy,
        MagaluHtmlStaticStrategy,
    ]:
        monkeypatch.setattr(cls, "get_data", fake_html_get_data)

class FakeMercadoLivreStrategy(ScrapingStrategy):
    """ Estratégia fictícia utilizada apenas para testes. """

    priority = 10

    def supports_url(self, url: str) -> bool:
        """ Suporta apenas URLs do Mercado Livre """
        return "mercadolivre.com.br" in url

    async def get_data(
        self,
        *,
        url: str,
        user_id,
        payload,
        product_type,
        rate_limiter=None,
        circuit_breaker=None,
        recovery_manager=None,
    ) -> dict:
        """ Retorna dados simulados de produto """
        return {
            "status": "success",
            "details": {"name": "Produto ML", "current_price": "RS 10,00"}
        }

def test_seleciona_estrategia_mercado_livre(monkeypatch) -> None:
    """ Garante que URLs do Mercado Livre utilizam a estratégia customizada """
    _preparar_ambiente(monkeypatch)
    chamada = {"executada": False}

    async def fake_get_data(self, **kwargs):
        chamada["executada"] = True
        return {
            "status": "success",
            "details": {"name": "Produto ML", "current_price": "R$ 10,00"},
        }

    monkeypatch.setattr(FakeMercadoLivreStrategy, "get_data", fake_get_data)
    monkeypatch.setattr(
        domain_policy,
        "STRATEGY_REGISTRY",
        {"FAKE": FakeMercadoLivreStrategy}
    )
    monkeypatch.setattr(
        domain_policy,
        "DOMAIN_POLICIES",
        {"mercadolivre.com.br": ["FAKE"]},
    )

    client = TestClient(app)
    resp = client.post(
        "/scrape/parse", json={"url": "https://www.mercadolivre.com.br/MLB-1"}
    )
    assert resp.status_code == 200
    assert chamada["executada"]

def test_seleciona_estrategia_amazon(monkeypatch) -> None:
    """ Garante que URLs da Amazon utilizam a estratégia correta """
    _preparar_ambiente(monkeypatch)

    escolhido: dict[str, Any] = {}
    original = common.strategies_for

    def capturar(url: str):
        resultado = original(url)
        #Armazena a sequência de estratégias escolhidas para verificação
        escolhido["estrategias"] = resultado
        return resultado

    monkeypatch.setattr(common, "strategies_for", capturar)
    client = TestClient(app)
    resp = client.post(
        "/scrape/parse", json={"url": "https://www.amazon.com.br/dp/ABC123"}
    )
    assert resp.status_code == 200
    assert escolhido["estrategias"][0].__class__.__name__ == "AmazonJsonStrategy"
    assert escolhido["estrategias"][1].__class__.__name__ == "AmazonHtmlStaticStrategy"

def test_seleciona_estrategia_shopee(monkeypatch) -> None:
    """ Garante que URLs da Shopee utilizam a estratégia correta """
    _preparar_ambiente(monkeypatch)
    escolhido: dict[str, Any] = {}
    original = common.strategies_for

    def capturar(url: str):
        resultado = original(url)
        escolhido["estrategias"] = resultado
        return resultado

    monkeypatch.setattr(common, "strategies_for", capturar)
    client = TestClient(app)
    resp = client.post(
        "/scrape/parse", json={"url": "https://shopee.com.br/produto-i.1.2"}
    )
    assert resp.status_code == 200
    assert escolhido["estrategias"][0].__class__.__name__ == "ShopeeJsonStrategy"
    assert escolhido["estrategias"][1].__class__.__name__ == "ShopeeHtmlStaticStrategy"

def test_seleciona_estrategia_magalu(monkeypatch) -> None:
    """ Garante que URLs da Magalu utilizam a estratégia correta """
    _preparar_ambiente(monkeypatch)
    escolhido: dict[str, Any] = {}
    original = common.strategies_for

    def capturar(url: str):
        resultado = original(url)
        escolhido["estrategias"] = resultado
        return resultado

    monkeypatch.setattr(common, "strategies_for", capturar)
    client = TestClient(app)
    resp = client.post(
        "/scrape/parse", json={"url": "https://www.magazineluiza.com.br/produto/p/abc123"}
    )
    assert resp.status_code == 200
    assert escolhido["estrategias"][0].__class__.__name__ == "MagaluJsonStrategy"
    assert escolhido["estrategias"][1].__class__.__name__ == "MagaluHtmlStaticStrategy"
