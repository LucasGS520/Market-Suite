""" Testes de integração do endpoint ``POST /parse`` com fixtures HTML reais """

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from market_scraper.main import app
from market_scraper.services import pipeline_steps
from market_scraper.utils import http_utils, url_validation

from shared.metrics.metrics_scraper import (
    SCRAPER_NO_RESULT_TOTAL,
    SCRAPER_STEP_FALLBACK_TOTAL,
    SCRAPER_STEP_LATENCY_SECONDS,
    SCRAPER_STEP_SUCCESS_TOTAL,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURES = {
    "amazon": FIXTURE_ROOT / "amazon" / "product_jsonld.html",
    "mercadolivre": FIXTURE_ROOT / "mercadolivre" / "product_static.html",
    "magazineluiza": FIXTURE_ROOT / "magazineluiza" / "product_js_only.html",
}

def _load_html(fixture_key: str) -> str:
    """ Lê o HTML de teste associado ao domínio informado """
    return FIXTURES[fixture_key].read_text(encoding="utf-8")

def _extract_metric(metrics_payload: str, metric: str, labels: dict[str, str]) -> float | None:
    """ Recupera o valor numérico de uma métrica Prometheus pelo conjunto de labels """
    for family in text_string_to_metric_families(metrics_payload):
        for sample in family.samples:
            if sample.name != metric:
                continue
            if all(sample.labels.get(key) == value for key, value in labels.items()):
                return float(sample.value)
    return None

def _reset_pipeline_metrics() -> None:
    """ Zera os contadores utilizados no cenários de integração """
    for metric in (
        SCRAPER_STEP_SUCCESS_TOTAL,
        SCRAPER_STEP_FALLBACK_TOTAL,
        SCRAPER_NO_RESULT_TOTAL,
        SCRAPER_STEP_LATENCY_SECONDS,
    ):
        metric.clear()

@pytest.fixture(autouse=True)
def _patch_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Evita resoluções DNS reais durante os testes de integração """
    fake_dns = lambda host: ["198.51.100.10"]
    monkeypatch.setattr(http_utils, "resolve_public_address", fake_dns)
    monkeypatch.setattr(url_validation, "resolve_public_address", fake_dns)

def test_parse_returns_payload_from_json_ld(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante sucesso quando a página contém JSON-LD válido """
    _reset_pipeline_metrics()
    client = TestClient(app)
    
    async def fake_download(_: str, *, timeout: float) -> str:
        return _load_html("amazon")

    monkeypatch.setattr(pipeline_steps, "download_html", fake_download)

    response = client.post(
        "/scrape/parse", 
        json={"url": "https://www.amazon.com.br/dp/B08N36XNTT"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "name": "Kindle Paperwhite Signature Edition",
        "current_price": "799.00",
        "url": "https://www.amazon.com.br/dp/B08N36XNTT",
        "source": "www.amazon.com.br",
    }

    metrics_payload = client.get("/metrics").text
    success_value = _extract_metric(
        metrics_payload,
        "scraper_step_success_total",
        {"domain": "www.amazon.com.br", "result": "success", "step": "json_ld_parser"},
    )
    assert success_value is not None and success_value >= 1.0


def test_parse_uses_html_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confere fallback quando JSON-LD está ausente e HTML estático resolve o preço """
    _reset_pipeline_metrics()
    client = TestClient(app)
    
    async def fake_download(_: str, *, timeout: float) -> str:
        return _load_html("mercadolivre")
    
    monkeypatch.setattr(pipeline_steps, "download_html", fake_download)

    response = client.post(
        "/scrape/parse",
        json={"url": "https://produto.mercadolivre.com.br/MLB-123456789"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "name": "Console Retro Game",
        "current_price": "549.90",
        "url": "https://produto.mercadolivre.com.br/MLB-123456789",
        "source": "produto.mercadolivre.com.br",
    }

    metrics_payload = client.get("/metrics").text
    fallback_value = _extract_metric(
        metrics_payload,
        "scraper_step_fallback_total",
        {"domain": "produto.mercadolivre.com.br", "result": "empty", "step": "json_ld_parser"},
    )
    assert fallback_value is not None and fallback_value >= 1.0
    success_value = _extract_metric(
        metrics_payload,
        "scraper_step_success_total",
        {"domain": "produto.mercadolivre.com.br", "result": "success", "step": "html_metadata_parser"},
    )
    assert success_value is not None and success_value >= 1.0


def test_parse_records_no_result_for_js_only_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida resposta 422 e incremento de métrica quando a página depende de JavaScript"""
    _reset_pipeline_metrics()
    client = TestClient(app)

    async def fake_download(_: str, *, timeout: float) -> str:
        return _load_html("magazineluiza")

    monkeypatch.setattr(pipeline_steps, "download_html", fake_download)

    response = client.post(
        "/scrape/parse",
        json={"url": "https://www.magazineluiza.com.br/p/abc123"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "message": "Não foi possível extrair dados do produto",
        "code": "no_result",
    }

    metrics_payload = client.get("/metrics").text
    no_result_value = _extract_metric(
        metrics_payload,
        "scraper_no_result_total",
        {"domain": "www.magazineluiza.com.br", "result": "no_result"},
    )
    assert no_result_value is not None and no_result_value >= 1.0
