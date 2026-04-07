""" Testes unitarios para snapshots materiais de comparacao. """

import pytest

from market_alert.comparisons.utils.snapshot_comparator import (
    extract_material_snapshot,
    snapshot_has_changed,
)


pytestmark = pytest.mark.unit


def test_extract_material_snapshot_ignores_non_material_fields() -> None:
    payload = {
        "monitored_price": 100,
        "competitiveness_status": "urgent",
        "computed_at": "2026-04-07T00:00:00Z",
    }

    snapshot = extract_material_snapshot(payload)

    assert snapshot["monitored_price"] == 100
    assert snapshot["competitiveness_status"] == "urgent"
    assert "computed_at" not in snapshot


def test_extract_material_snapshot_returns_empty_dict_for_non_mapping() -> None:
    assert extract_material_snapshot(["invalid"]) == {}


def test_snapshot_has_changed_returns_true_without_previous_snapshot() -> None:
    assert snapshot_has_changed({"monitored_price": 100}, None) is True


def test_snapshot_has_changed_returns_false_for_identical_snapshots() -> None:
    snapshot = {"monitored_price": 100, "competitiveness_status": "competitive"}

    assert snapshot_has_changed(snapshot, dict(snapshot)) is False


def test_snapshot_has_changed_detects_material_difference() -> None:
    current = {"monitored_price": 100, "competitiveness_status": "urgent"}
    previous = {"monitored_price": 90, "competitiveness_status": "competitive"}

    assert snapshot_has_changed(current, previous) is True
