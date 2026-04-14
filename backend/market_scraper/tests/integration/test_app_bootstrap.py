from __future__ import annotations


def test_market_scraper_app_bootstraps_with_registered_routes():
    from market_scraper.main import app

    route_paths = {route.path for route in app.routes}

    assert app.title == "MarketScraper"
    assert "/health/ping" in route_paths
    assert "/scraper/parse" in route_paths
