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
        SCRAPER_HEADERS_DEFAULT_COOKIES="session=abc||invalid||=skip||region=br",
        SCRAPER_HEADERS_ADDITIONAL="X-Test=1||X-Trace=trace-123",
        SCRAPER_HTTP_DOMAIN_TIMEOUTS="shop.example=4.5||bad||api.example=2",
    )

    assert settings.SCRAPER_STEP_TIMEOUT_SECONDS == 7.5
    assert settings.SCRAPER_PIPELINE_TIMEOUT_SECONDS == 12.0
    assert settings.SCRAPER_PIPELINE_TIMEOUT_SECONDS > settings.SCRAPER_STEP_TIMEOUT_SECONDS
    assert settings.get_default_cookies() == {"session": "abc", "region": "br"}
    assert settings.get_additional_headers() == {
        "X-Test": "1",
        "X-Trace": "trace-123",
    }
    assert settings.resolve_domain_timeout("shop.example", 9.0) == 4.5
    assert settings.resolve_domain_timeout("missing.example", 9.0) == 9.0


def test_settings_default_user_agent_matches_first_pool_entry(fresh_scraper_settings):
    settings = fresh_scraper_settings()

    assert settings.SCRAPER_USER_AGENT_POOL
    assert settings.SCRAPER_DEFAULT_USER_AGENT == settings.SCRAPER_USER_AGENT_POOL[0]
