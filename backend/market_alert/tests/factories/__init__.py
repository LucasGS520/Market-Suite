""" Factories padronizadas reutilizadas pela suite do market_alert. """

from market_alert.tests.factories.comparison_factories import ComparisonSnapshotFactory
from market_alert.tests.factories.product_factories import (
    CompetitorProductPayloadFactory,
    MonitoredProductPayloadFactory,
)
from market_alert.tests.factories.user_factories import UserPayloadFactory


__all__ = [
    "ComparisonSnapshotFactory",
    "CompetitorProductPayloadFactory",
    "MonitoredProductPayloadFactory",
    "UserPayloadFactory",
]
