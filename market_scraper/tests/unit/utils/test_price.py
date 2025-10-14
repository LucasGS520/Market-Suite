from decimal import Decimal

import pytest

from market_scraper.core.config_scraper import settings
from market_scraper.utils.price import format_decimal_to_str, parse_price_str
from shared.metrics.metrics_scraper import SCRAPER_PRICE_PARSER_USAGE_TOTAL


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

def _get_price_parser_metric(outcome: str) -> float:
    """ Recupera o valor atual da métrica do price-parser para um resultado """
    for metric in SCRAPER_PRICE_PARSER_USAGE_TOTAL.collect():
        for sample in metric.samples:
            if sample.labels.get("outcome") == outcome:
                return sample.value
    return 0.0

def test_parse_price_str_uses_price_parser_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SCRAPER_USE_PRICE_PARSER", True)
    class _Parsed:
        amount = "321.45"

    monkeypatch.setattr("market_scraper.utils.price.Price.fromstring", lambda _: _Parsed())

    before = _get_price_parser_metric("parsed")
    value = parse_price_str("qualquer", "http://example.com")
    after = _get_price_parser_metric("parsed")

    assert value == Decimal("321.45")
    assert after == pytest.approx(before + 1)

def test_parse_price_str_fallbacks_when_price_parser_missing_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SCRAPER_USE_PRICE_PARSER", True)
    class _Parsed:
        amount = None

    monkeypatch.setattr("market_scraper.utils.price.Price.fromstring", lambda _: _Parsed())

    before_missing = _get_price_parser_metric("missing_amount")
    value = parse_price_str("R$ 1.234,56", "http://example.com")
    after_missing = _get_price_parser_metric("missing_amount")

    assert value == Decimal("1234.56")
    assert after_missing == pytest.approx(before_missing + 1)
    