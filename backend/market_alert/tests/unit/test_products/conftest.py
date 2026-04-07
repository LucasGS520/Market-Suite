from __future__ import annotations

import pytest


@pytest.fixture
def monitored_product_payload(build_monitored_product_payload):
    return build_monitored_product_payload()


@pytest.fixture
def competitor_product_payload(build_competitor_product_payload, monitored_product_payload):
    return build_competitor_product_payload(
        monitored_product_id=monitored_product_payload["id"]
    )
