from __future__ import annotations

import os


def test_fresh_scraper_settings_uses_local_test_env(
    fresh_scraper_settings,
    scraper_test_paths,
    monkeypatch,
):
    monkeypatch.setenv("ENV_FILE", "ignored-by-tests.env")
    settings = fresh_scraper_settings()

    assert "env_file" not in scraper_test_paths
    assert os.environ["ENV_FILE"] == "ignored-by-tests.env"
    assert settings.SCRAPER_CACHE_TTL_SECONDS == 60
    assert settings.SCRAPER_HTTP_TIMEOUT_CONNECT == 0.5
    assert settings.SCRAPER_HTTP_RETRIES == 0
