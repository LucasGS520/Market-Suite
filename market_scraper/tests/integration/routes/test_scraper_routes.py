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
            }
        }

    #Substitui as funções reais pelo comportamento simulado
    monkeypatch.setattr("market_scraper.routes.routes_scraper.scrape_product_common_async", fake_scrape_product_common_async)

    payload = {"url": "www.mercadolivre.com.br/MLB-1"}

    #Primeira chamada: cache vazio, HTML deve ser armazenado
    resp1 = client.post("/scrape/parse", json=payload)
    assert resp1.status_code == 200
    assert contador == {"get": 1, "set": 1}
    corpo = resp1.json()
    assert corpo["name"] == "Produto Teste"
    #Verifica que o valor é serializado como string e mantém a precisão
    assert Decimal(corpo["current_price"]) == Decimal("10.00")
    assert corpo["marketplace"] == "www.mercadolivre.com.br"
    #Confirma que o esquema HTTPS foi adicionado automaticamente
    assert "https://www.mercadolivre.com.br/MLB-1" in cache

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

    payload = {"url": "www.amazon.com.br/dp/ABC123", "product_type": "competitor"}

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
    assert dados["marketplace"] == "www.amazon.com.br"

def test_parse_endpoint_not_monitored(monkeypatch) -> None:
    client = TestClient(app)

    #Retorno simulado indicando que não houve modificação no conteúdo
    async def fake_scrape_product_common_async(*a, **k):
        return {"status": "NOT_MODIFIED"}

    monkeypatch.setattr("market_scraper.routes.routes_scraper.scrape_product_common_async", fake_scrape_product_common_async)

    payload = {"url": "www.mercadolivre.com.br/MLB-1"}

    resp = client.post("/scrape/parse", json=payload)
    #Como nada muda, o endpoint deve responder com 304 sem corpo
    assert resp.status_code == 304
    assert resp.text == ""

def test_parse_endpoint_erro_estrategia(monkeypatch) -> None:
    client = TestClient(app)

    async def fake_scrape_product_common_async(*a, **k):
        return {"status": "error", "message": "falha simulada"}

    monkeypatch.setattr("market_scraper.routes.routes_scraper.scrape_product_common_async", fake_scrape_product_common_async)

    payload = {"url": "www.mercadolivre.com.br/MLB-1"}
    resp = client.post("/scrape/parse", json=payload)
    assert resp.status_code == 422
    assert resp.json() == {"detail": "falha simulada"}

def test_parse_endpoint_erro_detail(monkeypatch) -> None:
    client = TestClient(app)

    #Simula retorno de falha com chave ``detail``
    async def fake_scrape_product_common_async(*a, **k):
        return {"status": "error", "detail": "motivo"}

    #Substitui a função real pela versão simulada
    monkeypatch.setattr("market_scraper.routes.routes_scraper.scrape_product_common_async", fake_scrape_product_common_async)

    payload = {"url": "www.mercadolivre.com.br/MLB-1"}
    resp = client.post("/scrape/parse", json=payload)

    #O endpoint deve responder com 422 e repassar a mensagem de ``detail``
    assert resp.status_code == 422
    assert resp.json() == {"detail": "motivo"}

def test_parse_endpoint_url_invalida() -> None:
    client = TestClient(app)

    resp = client.post("/scrape/parse", json={"url": ""})
    assert resp.status_code == 400
    assert resp.json() == {"detail": "URL inválida ou malformada"}

def test_parse_endpoint_dominio_nao_suportado() -> None:
    client = TestClient(app)

    resp = client.post("/scrape/parse", json={"url": "https://dominioinexistente.com/produto"})
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Marketplace ainda não suportado"}

def test_parse_endpoint_url_sem_produto() -> None:
    client = TestClient(app)

    resp = client.post("/scrape/parse", json={"url": "www.mercadolivre.com.br/ofertas"})
    assert resp.status_code == 400
    assert resp.json() == {"detail": "A URL informada não corresponde a um produto"}
