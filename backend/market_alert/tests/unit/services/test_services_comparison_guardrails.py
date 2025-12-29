""" Testes de robustez para cálculos de resumo de comparação """

from datetime import datetime, timezone

from market_alert.services import services_comparison as comparison_service


def test_compute_summary_handles_none_payload_without_exploding():
    """Retorna resumo vazio e timestamps quando o payload está ausente."""

    timestamp = datetime.now(timezone.utc)
    summary = comparison_service._compute_summary_from_payload(  # pylint: disable=protected-access
        None, timestamp=timestamp, comparison_id=None, competitors_count=0
    )

    assert summary["computed_at"] == timestamp
    assert summary["discrepancies"] == []
    assert summary["competitors_with_price_count"] == 0


def test_compute_summary_tolerates_partial_payloads():
    """Preserva campos quando apenas partes do payload chegam preenchidas."""

    timestamp = datetime.now(timezone.utc)
    payload = {
        "monitored_price": "10.00",
        "discrepancies": [
            {"price": "11.00"},
            {"price": "12.00"},
        ],
        "lowest_competitor": None,
    }

    summary = comparison_service._compute_summary_from_payload(  # pylint: disable=protected-access
        payload,
        timestamp=timestamp,
        comparison_id=None,
        competitors_count=2,
    )

    assert summary["monitored_price"] == comparison_service.Decimal("10.00")
    assert summary["competitors_with_price_count"] == 2
    assert summary["competitors_min"] == comparison_service.Decimal("11.00")
    assert summary["competitors_max"] == comparison_service.Decimal("12.00")
    assert summary["competitors_mean"] == comparison_service.Decimal("11.50")


def test_compute_summary_builds_insights_with_complete_payload():
    """Gera status competitivo quando payload contém preços válidos."""

    timestamp = datetime.now(timezone.utc)
    payload = {
        "monitored_price": "9.00",
        "discrepancies": [{"price": "9.50"}, {"price": "9.75"}],
        "lowest_competitor": {"price": "8.90"},
        "highest_competitor": {"price": "10.00"},
    }

    summary = comparison_service._compute_summary_from_payload(  # pylint: disable=protected-access
        payload,
        timestamp=timestamp,
        comparison_id=None,
        competitors_count=2,
    )

    assert summary["competitiveness_status"] == comparison_service.CompetitivenessStatus.ATTENTION.value
    assert summary["position_rank"] == 2
    assert summary["potential_adjustment"] == comparison_service.Decimal("0.10")
    