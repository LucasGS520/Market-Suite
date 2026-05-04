"""Testes unitários para PostProcessResult.is_useful.

Cobre os critérios canônicos implementados em PostProcessResult.is_useful:
  1. availability=False → True (indisponibilidade explícita é útil)
  2. name + current_price → True
  3. name + last_status="price_unavailable" → True (produto existe, preço não confiável)
  4. apenas name ou apenas price → False
  5. resultado completamente vazio → False
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from market_scraper.domain.dtos import PostProcessResult


def _result(**overrides) -> PostProcessResult:
    defaults = {
        "name": None,
        "current_price": None,
        "currency": None,
        "availability": None,
        "last_status": None,
        "url": "https://example.com/p",
        "source": "example.com",
    }
    defaults.update(overrides)
    return PostProcessResult(**defaults)


# ── Casos positivos ───────────────────────────────────────────────────────────

def test_availability_false_alone_is_useful():
    assert _result(availability=False).is_useful is True


def test_name_and_price_is_useful():
    result = _result(name="TV 55", current_price=Decimal("2999.90"))
    assert result.is_useful is True


def test_name_price_and_availability_true_is_useful():
    result = _result(name="TV", current_price=Decimal("999.00"), availability=True)
    assert result.is_useful is True


def test_name_availability_false_is_useful():
    result = _result(name="TV", availability=False)
    assert result.is_useful is True


# ── PRICE_UNAVAILABLE ────────────────────────────────────────────────────────

def test_name_with_price_unavailable_is_useful():
    result = _result(name="Notebook", last_status="price_unavailable")
    assert result.is_useful is True


def test_name_price_unavailable_ignores_price_field():
    """PRICE_UNAVAILABLE não depende de current_price — price já foi descartado."""
    result = _result(name="Notebook", current_price=None, last_status="price_unavailable")
    assert result.is_useful is True


def test_no_name_price_unavailable_not_useful():
    """Sem nome, price_unavailable sozinho não é útil."""
    result = _result(last_status="price_unavailable")
    assert result.is_useful is False


# ── Casos negativos ───────────────────────────────────────────────────────────

def test_empty_result_not_useful():
    assert _result().is_useful is False


def test_name_only_not_useful():
    assert _result(name="Produto").is_useful is False


def test_price_only_not_useful():
    assert _result(current_price=Decimal("49.90")).is_useful is False


def test_availability_true_without_name_price_not_useful():
    assert _result(availability=True).is_useful is False


def test_availability_none_without_name_price_not_useful():
    assert _result(availability=None).is_useful is False


# ── Consistência com PostProcessResult.is_useful ──────────────────────────────

@pytest.mark.parametrize("name,price,avail", [
    (None, None, None),
    ("TV", None, None),
    (None, Decimal("100"), None),
    ("TV", Decimal("100"), None),
    (None, None, False),
])
def test_is_useful_matches_expected_rule(name, price, avail):
    result = _result(name=name, current_price=price, availability=avail)
    expected = avail is False or (bool(name) and price is not None)
    assert result.is_useful == expected
