from __future__ import annotations

from typing import Any

""" Testes de seleção dinâmica de estratégias de scraping """

from fastapi.testclient import TestClient
import pytest

from market_scraper.main import app
from market_scraper.strategies.base import ScrapingStrategy, register_strategy
from market_scraper.strategies import base as strategy_base
from market_scraper.strategies.playwright_default import PlaywrightDefaultStrategy


def _preparar_ambiente(monkeypatch) -> None:
    """ Configura dependências para evitar operações externas nos testes """
    #Desabilita uso real de cache
    monkeypatch.setattr("market_scraper.services.services_scraper_common.cache_manager.get", lambda *a, **k: None)
    monkeypatch.setattr("market_scraper.services_scraper_common.cache_manager.set", lambda *a, **k: None)

    #Evita navegação real pelo Playwright
    async def fake_default_get_data(
        self,
        *,
        url,
        user_id,
        payload,
        product_type,
        rate_limiter=None,
        circuit_breaker=None,
        recovery_manager=None,
    ) -> dict:
        return {"details": {"name": "Fake", "current_price": "R$ 0,00"}}

    monkeypatch.setattr(
        PlaywrightDefaultStrategy,
        "get_data",
        fake_default_get_data,
    )

class FakeMercadoLivreStrategy(ScrapingStrategy):
    """ Estratégia fictícia utilizada apenas para testes. """

    priority = 10

    def supports_url(self, url: str) -> bool:
        """ Suporta apenas URLs do Mercado Livre """
        return "mercadolivre.com" in url

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
            "details": {
                "name": "Produto ML",
                "current_price": "RS 10,00"
            }
        }

def test_seleciona_estrategia_mercado_livre(monkeypatch) -> None:
    """ Garante que URLs do Mercado Livre utilizam a estratégia e o padrão """
    _preparar_ambiente(monkeypatch)
    #Limpa estratégias registradas e adiciona a fictícia e a padrão
    monkeypatch.setattr(strategy_base, "_STRATEGIES", [])
    chamada = {"executada": False}

    async def fake_get_data(self, **kwargs):
        chamada["executada"] = True
        return {
            "details": {
                "name": "Produto ML",
                "current_price": "R$ 10,00",
            }
        }

    monkeypatch.setattr(FakeMercadoLivreStrategy, "get_data", fake_get_data)
    register_strategy(FakeMercadoLivreStrategy())
    register_strategy(PlaywrightDefaultStrategy())

    client = TestClient(app)
    resp = client.post(
        "/scrape/parse", json={"url": "https://www.mercadolivre.com.br/item/1"}
    )
    assert resp.status_code == 200
    assert chamada["executada"]

@pytest.mark.xfail(reason="Estratégia da Amazon ainda não implementada")
def test_seleciona_estrategia_amazon(monkeypatch) -> None:
    """ Teste placeholder para o domínio da Amazon """
    _preparar_ambiente(monkeypatch)
    from market_scraper.services import services_scraper_common as common

    escolhido = {}
    original = common.get_strategy_for_url

    def capturar(url: str):
        escolhido["estrategia"] = original(url)
        return escolhido["estrategia"]

    monkeypatch.setattr(common, "get_strategy_for_url", capturar)
    client = TestClient(app)
    resp = client.post(
        "/scrape/parse", json={"url": "https://shoppe.com.br/produto"}
    )
    assert resp.status_code == 200
    assert escolhido["estrategia"].__class__.__name__ == "ShoppeStrategy"

@pytest.mark.xfail(reason="Estratégia da Magalu ainda não implementada")
def test_seleciona_estrategia_magalu(monkeypatch) -> None:
    """ Teste placeholder para o domínio da Magalu """
    _preparar_ambiente(monkeypatch)
    from market_scraper.services import services_scraper_common as common

    escolhido = {}
    original = common.get_strategy_for_url

    def capturar(url: str):
        escolhido["estrategia"] = original(url)
        return escolhido["estrategia"]

    monkeypatch.setattr(common, "get_strategy_for_url", capturar)
    client = TestClient(app)
    resp = client.post(
        "/scrape/parse", json={"url": "https://www.magazineluiza.com.br/produto"}
    )
    assert resp.status_code == 200
    assert escolhido["estrategia"].__class__.__name__ == "MagaluStrategy"
