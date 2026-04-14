from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import market_alert.comparisons.services.services_comparison as comparison_service_module


pytestmark = pytest.mark.unit


def test_run_price_comparison_marks_missing_monitored_price_as_upstream_collection_failed(
    monkeypatch,
) -> None:
    monitored_id = uuid4()
    user_id = uuid4()
    comparison_id = uuid4()
    persisted_summaries: list[dict[str, object]] = []
    monitored = SimpleNamespace(
        id=monitored_id,
        user_id=user_id,
        paused=False,
        availability=True,
        last_status=None,
        status="active",
        current_price=None,
    )

    monkeypatch.setattr(
        comparison_service_module,
        "load_monitored_and_competitors",
        lambda db, monitored_uuid: (monitored, [], [], 0),
    )
    monkeypatch.setattr(
        comparison_service_module,
        "create_price_comparison",
        lambda db, monitored_uuid, payload, competitors_with_price_count, completed_at: SimpleNamespace(
            id=comparison_id,
            timestamp=datetime.now(timezone.utc),
        ),
    )
    monkeypatch.setattr(
        comparison_service_module,
        "upsert_price_comparison_summary",
        lambda db, monitored_uuid, stored_comparison_id, payload: persisted_summaries.append(payload),
    )

    result = comparison_service_module.run_price_comparison(SimpleNamespace(), monitored_id)

    assert result["summary"]["reason"] == "monitored_without_price"
    assert result["summary"]["upstream_reason"] == "upstream_collection_failed"
    assert result["summary"]["ignored_due_to_inactive"] is True
    assert persisted_summaries[-1]["upstream_reason"] == "upstream_collection_failed"
