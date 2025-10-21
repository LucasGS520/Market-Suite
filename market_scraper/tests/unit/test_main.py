""" Testes básicos dos endpoints principais da aplicação """

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from market_scraper.main import app
from market_scraper.services import pipeline_steps
from market_scraper.utils import url_validation


client = TestClient(app)
FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] 
    / "fixtures" 
    / "mercadolivre" 
    / "product_static.html"
)

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
    monkeypatch.setattr(url_validation, "resolve_public_addresses", lambda host: ["203.0.113.10"])

    payload = {"url": "mercadolivre.com.br/MLB-999"}
    response = client.post("/scrape/parse", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Console Retro Game"
    assert Decimal(body["current_price"]) == Decimal("549.90")
    assert body["source"] == "produto.mercadolivre.com.br"
