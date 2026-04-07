from __future__ import annotations

import pytest


@pytest.fixture
def collector_product_payload(build_monitored_product_payload):
    return build_monitored_product_payload()


@pytest.fixture
def scraper_snapshot_payload(collector_product_payload):
    return {
        "url": collector_product_payload["url"],
        "title": collector_product_payload["name"],
        "current_price": str(collector_product_payload["current_price"]),
        "currency": collector_product_payload["currency"],
        "availability": collector_product_payload["availability"],
    }
