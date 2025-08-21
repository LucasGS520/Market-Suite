from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from market_scraper.main import app


def test_parse_endpoint_com_cache(monkeypatch) -> None:
    client = TestClient(app)

    #Armazena o HTML em cache e controla quantas vezes cada função é chamada
    cache: dict[str, str] = {}
    contador = {"get": 0, "set": 0}

    def fake_get_cached_html(url: str, max_age: int = 300):
        contador["get"] += 1
        return cache.get(url)

    def fake_set_cached_html(url: str, html: str, ttl: int = 300) -> None:
        contador["set"] += 1
        cache[url] = html

    fake_html = "<html><body>Produto Teste</body></html>"

    async def fake_scrape_product_common_async(*, url, user_id, payload, product_type, **_: dict):
        html = fake_get_cached_html(url)
        if html is None:
            html = fake_html
            fake_set_cached_html(url, html)
        return {
            "details": {
                "name": "Produto Teste",
                "current_price": "R$ 10,00",
                "old_price": None,
                "thumbnail": "http://example.com/thumb.jpg",
                "shipping": "Frete Grátis",
                "seller": "Loja X",
            }
        }

    #Substitui as funções reais pelo comportamento simulado
    monkeypatch.setattr("market_scraper.routes.routes_scraper.scrape_product_common_async", fake_scrape_product_common_async)
    monkeypatch.setattr("market_scraper.services.services_cache_scraper.set_cached_html", fake_set_cached_html)

    payload = {"url": "http://example.com/item"}

    #Primeira chamada: cache vazio, HTML deve ser armazenado
    resp1 = client.post("/scrape/parse", json=payload)
    assert resp1.status_code == 200
    assert contador == {"get": 1, "set": 1}
    corpo = resp1.json()
    assert corpo["name"] == "Produto Teste"
    #Verifica que o valor é serializado como string e mantém a precisão
    assert Decimal(corpo["current_price"]) == Decimal("10.00")

    #Segunda chamada: HTML vem do cache e ``set_cached_html`` não é invocado
    resp2 = client.post("/scrape/parse", json=payload)
    assert resp2.status_code == 200
    assert contador == {"get": 2, "set": 1}

def test_parse_endpoint_competitor_not_monitored(monkeypatch) -> None:
    client = TestClient(app)

    async def fake_scrape_product_common_async(*a, **k):
        return {"details": {"name": "Produto X", "current_price": "R$ 5,00"}}

    def fake_monitored(*a, **k):
        raise AssertionError("MonitoredProductCreateScraping não deve ser usado")

    monkeypatch.setattr("market_scraper.routes.routes_scraper.scrape_product_common_async", fake_scrape_product_common_async)
    monkeypatch.setattr("market_scraper.routes.routes_scraper.MonitoredProductCreateScraping", fake_monitored)

    payload = {"url": "http://exemplo.com/item", "product_type": "competitor"}

    resp = client.post("/scrape/parse", json=payload)
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["name"] == "Produto X"
    assert Decimal(dados["current_price"]) == Decimal("5.00")
    assert dados["old_price"] is None
    assert dados["thumbnail"] is None
    assert dados["free_shipping"] is False
    assert dados["seller"] is None
    assert dados["shipping"] is None
