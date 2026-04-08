from __future__ import annotations

from shared.schemas.shared_schemas_scraper import ParserResponse

from market_scraper.services.pipeline_factory import run_pipeline


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
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
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
        "success",
        "empty",
        "empty",
        "empty",
        "success",
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
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
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
