""" Testes básicos dos endpoints principais da aplicação """

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
    async def fake_scrape_product_common(*args, **kwargs):
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

    monkeypatch.setattr("market_scraper.routes.routes_scraper._scrape_product_common", fake_scrape_product_common)

    payload = {"url": "http://example.com/produto"}
    response = client.post("/scrape/parse", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Produto Teste"
    assert body["current_price"] == 10.0
    assert body["free_shipping"] is True
