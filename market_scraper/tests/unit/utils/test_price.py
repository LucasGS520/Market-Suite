import pytest
from decimal import Decimal
from fastapi import HTTPException
from scraper_app.utils.price import parse_price_str


def test_parse_price_str_valid():
    value = parse_price_str("R$ 1.234,56", "http://example.com")
    assert value == Decimal("1234.56")

@pytest.mark.parametrize("raw", ["", "  ", None, "abc"])
def test_parse_price_str_invalid(raw):
    with pytest.raises(HTTPException):
        parse_price_str(raw, "http://example.com")
