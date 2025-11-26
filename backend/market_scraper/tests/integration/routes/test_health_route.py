from fastapi.testclient import TestClient

from market_scraper.main import app


def test_health_ping() -> None:
    client = TestClient(app)
    resposta = client.get("/health/ping")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
