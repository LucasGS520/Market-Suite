from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from shared.schemas.shared_schemas_orchestrator import (
    CollectionPayload,
    PolicyActivityOutput,
    validate_payload,
)
from shared.schemas.shared_schemas_products import (
    CompetitorProductCreateScraping,
    InitialCompetitorCreateScraping,
    MonitoredProductCreateScraping,
    ProductCore,
)
from shared.schemas.shared_schemas_scraper import (
    ParserRequest,
    ParserResponse,
    ScrapeResult,
)


pytestmark = pytest.mark.unit


def test_collection_payload_generates_trace_id_and_enforces_kind_rules():
    monitored_id = uuid4()
    user_id = uuid4()

    payload = CollectionPayload.model_validate(
        {
            "kind": "monitored",
            "monitored_id": monitored_id,
            "url": "https://example.com/product",
            "user_id": user_id,
        }
    )

    assert payload.trace_id
    assert payload.monitored_id == monitored_id
    assert payload.user_id == user_id

    with pytest.raises(ValueError, match="competitor_id"):
        CollectionPayload.model_validate(
            {
                "kind": "competitor",
                "monitored_id": monitored_id,
                "url": "https://example.com/product",
                "user_id": user_id,
            }
        )


def test_collection_payload_rejects_non_canonical_trace_id_and_validate_payload_wraps_errors():
    monitored_id = uuid4()
    user_id = uuid4()

    with pytest.raises(ValueError, match="UUID can.nico"):
        CollectionPayload.model_validate(
            {
                "kind": "monitored",
                "monitored_id": monitored_id,
                "url": "https://example.com/product",
                "trace_id": str(uuid4()).upper(),
                "user_id": user_id,
            }
        )

    with pytest.raises(ValueError, match="Payload de coleta inv.lido"):
        validate_payload(
            {
                "kind": "monitored",
                "monitored_id": monitored_id,
                "url": "https://example.com/product",
                "competitor_id": str(uuid4()),
                "trace_id": str(uuid4()),
                "user_id": user_id,
            }
        )


def test_policy_activity_output_ignores_unknown_fields():
    policy = PolicyActivityOutput.from_dict(
        {
            "interval_seconds": 120,
            "paused": True,
            "scheduling_reason": "manual",
            "unknown_field": "ignored",
        }
    )

    assert policy.interval_seconds == 120
    assert policy.paused is True
    assert policy.scheduling_reason == "manual"
    assert not hasattr(policy, "unknown_field")


def test_product_schemas_normalize_aliases_and_optional_names():
    product = ProductCore.model_validate(
        {
            "id": str(uuid4()),
            "url": "https://example.com/product",
            "name": "Produto",
            "price": "10.50",
            "source": "monitored",
        }
    )

    monitored = MonitoredProductCreateScraping.model_validate(
        {
            "name_identification": "   ",
            "product_url": "https://example.com/monitorado",
        }
    )
    initial_competitor = InitialCompetitorCreateScraping.model_validate(
        {
            "name": "  Loja A  ",
            "product_url": "https://example.com/concorrente",
        }
    )
    competitor = CompetitorProductCreateScraping.model_validate(
        {
            "monitored_product_id": str(uuid4()),
            "product_url": "https://example.com/concorrente",
            "name": "   ",
        }
    )

    assert product.product_url.unicode_string() == "https://example.com/product"
    assert product.current_price == Decimal("10.50")
    assert monitored.name_identification is None
    assert initial_competitor.name == "Loja A"
    assert competitor.name is None


def test_parser_request_and_response_normalize_common_inputs():
    request = ParserRequest.model_validate(
        {
            "url": "example.com/product",
            "metadata": {},
            "product_type": "competitor",
        }
    )
    response = ParserResponse.model_validate(
        {
            "name": "  Produto X  ",
            "current_price": "0",
            "marketplace": "example",
            "url": "https://example.com/product",
        }
    )

    assert request.url.unicode_string() == "https://example.com/product"
    assert request.metadata is None
    assert response.name == "Produto X"
    assert response.current_price is None
    assert response.last_status == "price_zero_filtered"
    assert response.source == "example"
    assert response.url.unicode_string() == "https://example.com/product"


def test_scrape_result_supports_mapping_style_access():
    persisted_at = datetime.now(timezone.utc)
    result = ScrapeResult(status="success", http_status=200, persisted_at=persisted_at)

    assert result["status"] == "success"
    assert result["http_status"] == 200
    assert result["persisted_at"] == persisted_at
