from __future__ import annotations

import os


def test_fresh_scraper_settings_uses_local_test_env(
    fresh_scraper_settings,
    scraper_test_paths,
):
    settings = fresh_scraper_settings()
    env_file = os.environ["ENV_FILE"].replace("\\", "/")

    assert env_file == "market_scraper/.env.market_scraper.test"
    assert scraper_test_paths["env_file"].name == ".env.market_scraper.test"
    assert settings.SCRAPER_CACHE_TTL_SECONDS == 60
    assert settings.SCRAPER_HTTP_TIMEOUT_CONNECT == 0.5
    assert settings.SCRAPER_HTTP_RETRIES == 0
