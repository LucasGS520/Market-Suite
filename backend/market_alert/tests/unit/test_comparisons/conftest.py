from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.fixture
def comparison_snapshot(build_comparison_snapshot):
    return build_comparison_snapshot()


@pytest.fixture
def comparison_snapshot_attention(build_comparison_snapshot):
    return build_comparison_snapshot(
        monitored_price=Decimal("199.90"),
        competitor_prices=[Decimal("189.90"), Decimal("194.90")],
        competitor_availability=[True, True],
    )
