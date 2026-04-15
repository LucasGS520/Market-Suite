from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from market_scraper.services.pipeline_factory import run_pipeline


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


async def test_controlled_concurrent_volume_keeps_response_stable(monkeypatch):
    success_html = _load_fixture("product_success.html")
    download_calls = {"count": 0}

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_download(url: str, *, timeout: float) -> str:
        download_calls["count"] += 1
        await asyncio.sleep(0.01)
        return success_html

    from market_scraper.services.response_classifier import (
        ClassificationAction,
        ClassificationResult,
    )

    fake_rl = MagicMock()
    fake_rl.should_allow = AsyncMock(return_value=(True, 1))
    fake_rl.update_history = AsyncMock()

    fake_classifier = MagicMock()
    fake_classifier.classify = MagicMock(return_value=ClassificationResult(
        action=ClassificationAction.SUCCESS,
        next_layer=None,
        reason="html_ok",
    ))

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.adaptive_rate_limiter",
        fake_rl,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier",
        fake_classifier,
    )

    tasks = [
        run_pipeline("https://example.com/product/stability", trace_id=f"stress-{index}")
        for index in range(12)
    ]
    outcomes = await asyncio.gather(*tasks)

    assert download_calls["count"] == 1
    assert len(outcomes) == 12
    assert all(outcome.status == "success" for outcome in outcomes)
    assert all(outcome.payload is not None for outcome in outcomes)
    assert {
        (
            outcome.payload["name"],
            outcome.payload["current_price"],
            outcome.payload["source"],
        )
        for outcome in outcomes
    } == {("Notebook Integrado", "1999.90", "example.com")}
