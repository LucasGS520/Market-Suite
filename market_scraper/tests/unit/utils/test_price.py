""" Testes do utilitário de parsing de preços """

from decimal import Decimal

import pytest

from market_scraper.utils.price import format_decimal_to_str, parse_price_str
from shared.metrics.metrics_scraper import SCRAPER_PRICE_PARSER_USAGE_TOTAL


def test_parse_price_str_valid() -> None:
    """ Garante interpretação correta com separadores de milhar e moeda """
    value = parse_price_str("R$ 1.234,56", "http://example.com")
    assert value == Decimal("1234.56")

@pytest.mark.parametrize("raw", ["", "  ", None, "abc"])
def test_parse_price_str_invalid(raw) -> None:
    """ Confirma que valores vazios ou não numéricos geram erro """
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
    """ Aceita tipos numéricos já estruturados sem alterar valor """
    value = parse_price_str(raw, "http://example.com")
    assert value == expected

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1.234,56", Decimal("1234.56")),
        ("US$ 1,234.56", Decimal("1234.56")),
        ("€ 2.345,00", Decimal("2345.00")),
        ("R$12 345,99", Decimal("12345.99")),
        ("Preço: 9,99", Decimal("9.99")),
    ],
)
def test_parse_price_str_multiple_textual_formats(raw: str, expected: Decimal) -> None:
    """ Valida diferentes combinações de moeda, milhar e espaços """
    value = parse_price_str(raw, "http://example.com")
    assert value == expected

def test_format_decimal_to_str() -> None:
    """ Formata ``Decimal`` com arredondamento convencional """
    formatted = format_decimal_to_str(Decimal("12.345"))
    assert formatted == "12.35"

def _get_price_parser_metric(outcome: str) -> float:
    """ Recupera o valor atual da métrica do price-parser para um resultado """
    for metric in SCRAPER_PRICE_PARSER_USAGE_TOTAL.collect():
        for sample in metric.samples:
            if sample.labels.get("outcome") == outcome:
                return sample.value
    return 0.0

def test_parse_price_str_uses_price_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confirma incremento de métricas quando ``price-parser`` resolve """
    class _Parsed:
        amount = "321.45"

    monkeypatch.setattr("market_scraper.utils.price.Price.fromstring", lambda _: _Parsed())

    before = _get_price_parser_metric("parsed")
    value = parse_price_str("qualquer", "http://example.com")
    after = _get_price_parser_metric("parsed")

    assert value == Decimal("321.45")
    assert after == pytest.approx(before + 1)

def test_parse_price_str_fallbacks_when_missing_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Mede fallback manual quando ``price-parser`` não retorna amount """
    class _Parsed:
        amount = None

    monkeypatch.setattr("market_scraper.utils.price.Price.fromstring", lambda _: _Parsed())

    before_missing = _get_price_parser_metric("missing_amount")
    before_fallback = _get_price_parser_metric("fallback")

    value = parse_price_str("R$ 1.234,56", "http://example.com")
    
    after_missing = _get_price_parser_metric("missing_amount")
    after_fallback = _get_price_parser_metric("fallback")

    assert value == Decimal("1234.56")
    assert after_missing == pytest.approx(before_missing + 1)
    
    assert after_fallback == pytest.approx(before_fallback + 1)

def test_parse_price_str_fallbacks_when_parser_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante fallback manual quando o parser lança exceção """
    def _raise(_: str) -> None:
        raise RuntimeError("falha simulada")
    
    monkeypatch.setattr("market_scraper.utils.price.Price.fromstring", _raise)

    before_error = _get_price_parser_metric("error")
    before_fallback = _get_price_parser_metric("fallback")

    value = parse_price_str("R$ 777,70", "http://example.com")

    after_error = _get_price_parser_metric("error")
    after_fallback = _get_price_parser_metric("fallback")

    assert value == Decimal("777.70")
    assert after_error == pytest.approx(before_error + 1)
    assert after_fallback == pytest.approx(before_fallback + 1)
