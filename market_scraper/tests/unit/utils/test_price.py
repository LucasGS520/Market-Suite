from decimal import Decimal

import pytest

from market_scraper.utils.price import format_decimal_to_str, parse_price_str


def test_parse_price_str_valid() -> None:
    value = parse_price_str("R$ 1.234,56", "http://example.com")
    assert value == Decimal("1234.56")

@pytest.mark.parametrize("raw", ["", "  ", None, "abc"])
def test_parse_price_str_invalid(raw) -> None:
    with pytest.raises(ValueError):
        parse_price_str(raw, "http://example.com")

@pytest.mark.parametrize(
    "raw, expected",
    [
        (100, Decimal("100")),
        (100.5, Decimal("100.5")),
        (Decimal("42.42"), Decimal("42.42")),
    ],
)
def test_parse_price_str_numeric_inputs(raw, expected) -> None:
    value = parse_price_str(raw, "http://example.com")
    assert value == expected

def test_format_decimal_to_str() -> None:
    formatted = format_decimal_to_str(Decimal("12.345"))
    assert formatted == "12.35"
