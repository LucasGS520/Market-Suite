""" Testes básicos dos endpoints principais da aplicação """

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from market_scraper.main import app
from market_scraper.services import pipeline_steps


client = TestClient(app)
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "html" / "sample_product.html"

def test_health_ping() -> None:
    """ Verifica se o endpoint de saúde responde com status ok """
    response = client.get("/health/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_scraper_parse(monkeypatch) -> None:
    """ Confere se o endpoint ``/parse`` entrega payload mínimo """
    async def fake_download(url: str, *, timeout: float) -> str:
        return FIXTURE_PATH.read_text(encoding="utf-8")
    
    monkeypatch.setattr(pipeline_steps, "download_html", fake_download)

    payload = {"url": "mercadolivre.com.br/MLB-999"}
    response = client.post("/scrape/parse", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Produto Genérico"
    assert Decimal(body["current_price"]) == Decimal("199.90")
