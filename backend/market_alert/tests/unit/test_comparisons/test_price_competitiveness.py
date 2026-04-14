""" Testes unitarios para calculo de competitividade de precos. """

from decimal import Decimal

import pytest

from market_alert.comparisons.domain.price_competitiveness import (
    ComparisonSnapshot,
    CompetitivenessThresholds,
    calculate_competitiveness,
    determine_competitiveness_status,
)
from market_alert.enums.enums_comparisons import CompetitivenessStatus


pytestmark = pytest.mark.unit


def test_determine_competitiveness_status_returns_competitive_for_non_positive_delta() -> None:
    status = determine_competitiveness_status(
        Decimal("-1.00"),
        CompetitivenessThresholds.defaults(),
    )

    assert status == CompetitivenessStatus.COMPETITIVE.value


def test_determine_competitiveness_status_returns_attention_within_threshold() -> None:
    status = determine_competitiveness_status(
        Decimal("3.00"),
        CompetitivenessThresholds.defaults(),
    )

    assert status == CompetitivenessStatus.ATTENTION.value


def test_calculate_competitiveness_returns_rank_mean_and_adjustment(comparison_snapshot) -> None:
    result = calculate_competitiveness(
        comparison_snapshot,
        CompetitivenessThresholds.defaults(),
    )

    assert result.status == CompetitivenessStatus.URGENT.value
    assert result.min_price == Decimal("189.90")
    assert result.max_price == Decimal("205.00")
    assert result.mean_price == Decimal("196.60")
    assert result.rank == 3
    assert result.adjustment == Decimal("10.00")


def test_calculate_competitiveness_raises_when_snapshot_is_invalid() -> None:
    snapshot = ComparisonSnapshot(monitored_price=None, competitor_prices=[])

    with pytest.raises(ValueError, match="ComparisonSnapshot inv"):
        calculate_competitiveness(snapshot, CompetitivenessThresholds.defaults())


def test_calculate_competitiveness_raises_when_no_competitor_is_available() -> None:
    snapshot = ComparisonSnapshot(
        monitored_price=Decimal("100.00"),
        competitor_prices=[Decimal("90.00")],
        competitor_availability=[False],
    )

    with pytest.raises(ValueError, match="Nenhum pre"):
        calculate_competitiveness(snapshot, CompetitivenessThresholds.defaults())
