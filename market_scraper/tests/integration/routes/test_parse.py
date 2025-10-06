""" Testes de integração do endpoint ``POST /parse`` """

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from market_scraper.main import app
from market_scraper.services import pipeline_steps
from market_scraper.utils import url_validation

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "html" / "sample_product.html"


def _load_html() -> str:
    """ Carrega o HTML fixo para simular o download da página """
    return FIXTURE_PATH.read_text(encoding="utf-8")

def test_parse_endpoint_returns_payload(monkeypatch) -> None:
    """ Garante que o endpoint processa a URL e retorna o payload essencial """
    client = TestClient(app)
    async def fake_download(url: str, *, timeout: float) -> str:
        return _load_html()
    
    #Substituimos a etapa de download para evitar chamadas externas durante o teste
    monkeypatch.setattr(pipeline_steps, "download_html", fake_download)
    #Fixamos a resolução DNS para impedir que o teste dependa de rede externa
    monkeypatch.setattr(url_validation, "resolve_public_address", lambda host: ["203.0.113.10"])

    response = client.post("/scrape/parse", json={"url": "mercadolivre.com.br/MLB-123"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Produto Genérico"
    assert body["url"] == "https://produto.mercadolivre.com.br/MLB-123"
    assert body["source"] == "produto.mercadolivre.com.br"
    assert body["current_price"] == "199.90"


def test_parse_endpoint_invalid_url() -> None:
    """ Valida o retorno padronizado para URLs inválidas """
    client = TestClient(app)
    response = client.post("/scrape/parse", json={"url": ""})
    assert response.status_code == 400
    assert response.json() == {"message": "URL inválida ou malformada", "code": "invalid_url"}
