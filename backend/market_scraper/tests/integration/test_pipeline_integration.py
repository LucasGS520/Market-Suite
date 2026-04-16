from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.schemas.shared_schemas_scraper import ParserResponse

from market_scraper.services.pipeline_factory import run_pipeline
from market_scraper.services.response_classifier import (
    ClassificationAction,
    ClassificationResult,
)


def _fake_rate_limiter() -> MagicMock:
    rl = MagicMock()
    rl.should_allow = AsyncMock(return_value=(True, 1))
    rl.update_history = AsyncMock()
    return rl


def _fake_classifier_success() -> MagicMock:
    cls = MagicMock()
    cls.classify = MagicMock(
        return_value=ClassificationResult(
            action=ClassificationAction.SUCCESS,
            next_layer=None,
            reason="html_ok",
        )
    )
    return cls


async def test_pipeline_sequential_flow_falls_back_to_generic_parser(
    monkeypatch,
    generic_fallback_html,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_download(url: str, *, timeout: float) -> str:
        return generic_fallback_html

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate._classifier",
        _fake_classifier_success(),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.parse_with_extruct",
        lambda html, url: None,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.parse_with_beautifulsoup",
        lambda html, url: None,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.get_domain_parser",
        lambda domain: None,
    )

    outcome = await run_pipeline("https://example.com/product/fallback")

    assert outcome.status == "success"
    assert outcome.payload is not None
    assert outcome.payload["name"] == "Fallback Integrado"
    assert outcome.payload["current_price"] == "349.90"
    assert [step.status for step in outcome.steps] == [
        "success",  # FetchHTMLStep
        "empty",    # JsonLdParserStep
        "empty",    # HtmlMetadataParserStep
        "empty",    # DomainSpecificParserStep
        "success",  # GenericFallbackParserStep
    ]


async def test_pipeline_success_payload_is_compatible_with_shared_parser_response(
    monkeypatch,
    success_product_html,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_download(url: str, *, timeout: float) -> str:
        return success_product_html

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate._classifier",
        _fake_classifier_success(),
    )

    outcome = await run_pipeline("https://example.com/product/contract")

    assert outcome.status == "success"
    response = ParserResponse.model_validate(
        {
            "name": outcome.payload["name"],
            "current_price": outcome.payload["current_price"],
            "url": outcome.payload["url"],
            "source": outcome.payload["source"],
            "currency": outcome.payload.get("currency"),
            "availability": outcome.payload.get("availability"),
            "last_status": outcome.payload.get("last_status"),
        }
    )
    assert response.name == "Notebook Integrado"
    assert str(response.url) == "https://example.com/product/notebook-integrado"


async def test_pipeline_playwright_fallback_resolves_challenge(
    monkeypatch,
    success_product_html,
    fixture_html_loader,
):
    """curl_cffi retorna página de challenge → classificador escala → Playwright entrega HTML válido.

    Verifica que o pipeline completa com sucesso e que a telemetria de fallback
    está correta: fallback_taken=True, anti_bot_detected=True, anti_bot_bypassed=True.
    """
    challenge_html = fixture_html_loader("response_js_challenge.html")

    call_count = {"n": 0}

    async def fake_download(url: str, *, timeout: float) -> str:
        # Primeira chamada → challenge; não deve haver segunda (Playwright é mockado)
        call_count["n"] += 1
        return challenge_html

    fake_pw_pool = MagicMock()
    fake_pw_pool.is_ready = True
    fake_pw_pool.fetch_html = AsyncMock(return_value=success_product_html)

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    # Classifier real: challenge_html contém "challenges.cloudflare.com" → SCALE
    # Não mockamos o classifier para validar a integração real com o HTML de fixture.
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.playwright_pool",
        fake_pw_pool,
    )

    outcome = await run_pipeline("https://example.com/product/challenge")

    assert outcome.status == "success"
    assert outcome.payload is not None
    assert outcome.payload["name"] == "Notebook Integrado"

    # Telemetria de fallback deve estar preenchida
    assert outcome.context.data.get("layer_used") == "playwright"
    assert outcome.context.data.get("fallback_taken") is True
    # anti_bot_bypassed=True: Playwright entregou HTML sem padrão residual
    assert outcome.context.data.get("anti_bot_bypassed") is True

    # download_html foi chamado exatamente uma vez (camada 1 apenas)
    assert call_count["n"] == 1
