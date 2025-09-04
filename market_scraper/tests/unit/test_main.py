""" Testes básicos dos endpoints principais da aplicação """

from decimal import Decimal

from fastapi.testclient import TestClient

from market_scraper.main import app


client = TestClient(app)

def test_health_ping() -> None:
    """ Verifica se o endpoint de saúde responde com status ok """
    response = client.get("/health/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_scraper_parse(monkeypatch) -> None:
    """ Garante que o endpoint de parsing retorna os campos esperados """
    async def fake_scrape_product_common_async(*a, **k):
        return {
            "details": {
                "name": "Produto Teste",
                "current_price": "R$ 10,00",
            }
        }

    monkeypatch.setattr("market_scraper.routes.routes_scraper.scrape_product_common_async", fake_scrape_product_common_async)

    #URL simulada de produto válida para passar pela validação
    payload = {"url": "www.mercadolivre.com.br/MLB-1"}
    response = client.post("/scrape/parse", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Produto Teste"
    assert Decimal(body["current_price"]) == Decimal("10.00")
