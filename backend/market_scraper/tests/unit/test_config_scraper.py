from __future__ import annotations

import dotenv


def test_settings_read_overrides_and_parse_composite_values(
    fresh_scraper_settings,
    monkeypatch,
):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    settings = fresh_scraper_settings(
        SCRAPER_STEP_TIMEOUT_SECONDS=7.5,
        SCRAPER_PIPELINE_TIMEOUT_SECONDS=12.0,
        SCRAPER_HTTP_DOMAIN_TIMEOUTS="shop.example=4.5||bad||api.example=2",
    )

    assert settings.SCRAPER_STEP_TIMEOUT_SECONDS == 7.5
    assert settings.SCRAPER_PIPELINE_TIMEOUT_SECONDS == 12.0
    assert settings.SCRAPER_PIPELINE_TIMEOUT_SECONDS > settings.SCRAPER_STEP_TIMEOUT_SECONDS
    assert settings.resolve_domain_timeout("shop.example", 9.0) == 4.5
    assert settings.resolve_domain_timeout("missing.example", 9.0) == 9.0
