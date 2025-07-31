from decimal import Decimal
from types import SimpleNamespace

from app.utils.comparator import compare_prices


def test_compare_prices_performance(benchmark):
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"), target_price=Decimal("9.00"))
    c1 = SimpleNamespace(id="c1", name_competitor="A", current_price=Decimal("8.00"))
    c2 = SimpleNamespace(id="c2", name_competitor="B", current_price=Decimal("11.00"))
    benchmark(compare_prices, monitored, [c1, c2])
