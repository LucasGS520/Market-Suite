from __future__ import annotations

from decimal import Decimal

import factory

from market_alert.comparisons.domain.price_competitiveness import ComparisonSnapshot


class ComparisonSnapshotFactory(factory.Factory):
    """ Snapshot padrao para testes de competitividade sem dependencias externas. """

    class Meta:
        model = ComparisonSnapshot

    monitored_price = Decimal("199.90")
    competitor_prices = factory.LazyFunction(
        lambda: [Decimal("189.90"), Decimal("194.90"), Decimal("205.00")]
    )
    competitor_availability = factory.LazyFunction(lambda: [True, True, True])
