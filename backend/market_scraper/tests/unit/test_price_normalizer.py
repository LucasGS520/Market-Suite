"""Testes unitários para PriceNormalizer.

Garante que:
  - valores válidos (string, int, float, Decimal, moeda BR) → Decimal correto
  - valores inválidos → None (sem exceção)
  - None → None
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from market_scraper.post_processing.normalizers.price_normalizer import PriceNormalizer

_URL = "https://example.com/produto"


@pytest.fixture
def normalizer() -> PriceNormalizer:
    return PriceNormalizer()


# ── Casos válidos ──────────────────────────────────────────────────────────────

def test_normalizes_simple_string(normalizer):
    result = normalizer.normalize("1299.90", _URL)
    assert result == Decimal("1299.90")


def test_normalizes_brazilian_currency_string(normalizer):
    result = normalizer.normalize("R$ 1.299,90", _URL)
    assert result == Decimal("1299.90")


def test_normalizes_integer(normalizer):
    result = normalizer.normalize(500, _URL)
    assert result == Decimal("500")


def test_normalizes_float(normalizer):
    result = normalizer.normalize(99.9, _URL)
    assert result is not None
    assert isinstance(result, Decimal)


def test_normalizes_decimal_passthrough(normalizer):
    value = Decimal("2499.00")
    assert normalizer.normalize(value, _URL) == value


def test_normalizes_zero_string(normalizer):
    result = normalizer.normalize("0", _URL)
    assert result == Decimal("0")


def test_normalizes_comma_decimal(normalizer):
    result = normalizer.normalize("3.499,00", _URL)
    assert result == Decimal("3499.00")


# ── Casos inválidos → None ──────────────────────────────────────────────────

def test_none_returns_none(normalizer):
    assert normalizer.normalize(None, _URL) is None


def test_empty_string_returns_none(normalizer):
    assert normalizer.normalize("", _URL) is None


def test_garbage_string_returns_none(normalizer):
    assert normalizer.normalize("sem-preco-aqui", _URL) is None


def test_does_not_raise_on_invalid_value(normalizer):
    try:
        result = normalizer.normalize("abc-xyz", _URL)
        assert result is None
    except Exception as exc:
        pytest.fail(f"PriceNormalizer levantou {exc!r} em valor inválido")
