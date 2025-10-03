from decimal import Decimal

import pytest

from market_scraper.utils.price import parse_price_str


def test_parse_price_str_valid() -> None:
    value = parse_price_str("R$ 1.234,56", "http://example.com")
    assert value == Decimal("1234.56")

@pytest.mark.parametrize("raw", ["", "  ", None, "abc"])
def test_parse_price_str_invalid(raw) -> None:
    with pytest.raises(ValueError):
        parse_price_str(raw, "http://example.com")
