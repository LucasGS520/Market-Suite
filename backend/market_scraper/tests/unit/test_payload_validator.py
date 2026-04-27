"""Testes unitários para is_useful_payload — validação de utilidade de payload.

Cobre os três critérios canônicos:
  1. payload None ou vazio → False
  2. availability=False → True (indisponibilidade explícita é útil por si só)
  3. name + current_price → True
  4. name sem preço → False
  5. preço sem nome → False
"""

from __future__ import annotations

import pytest

from market_scraper.utils.validator import is_useful_payload


# ── Casos negativos ───────────────────────────────────────────────────────────

def test_none_payload_returns_false():
    assert is_useful_payload(None) is False


def test_empty_dict_returns_false():
    assert is_useful_payload({}) is False


def test_name_only_returns_false():
    assert is_useful_payload({"name": "Produto X"}) is False


def test_price_only_returns_false():
    assert is_useful_payload({"current_price": "99.90"}) is False


def test_availability_true_without_name_price_returns_false():
    assert is_useful_payload({"availability": True}) is False


# ── Casos positivos ───────────────────────────────────────────────────────────

def test_availability_false_alone_returns_true():
    """Indisponibilidade explícita é útil mesmo sem nome ou preço."""
    assert is_useful_payload({"availability": False}) is True


def test_availability_false_overrides_missing_price():
    assert is_useful_payload({"name": "TV", "availability": False}) is True


def test_name_and_price_returns_true():
    assert is_useful_payload({"name": "Console", "current_price": "2999.90"}) is True


def test_name_and_price_with_extra_fields_returns_true():
    assert is_useful_payload({
        "name": "Notebook",
        "current_price": "4500.00",
        "url": "https://loja.com/nb",
        "source": "loja.com",
        "availability": True,
    }) is True


def test_price_zero_string_counts_as_present():
    """Preço "0" é um valor presente — validador não filtra semânticamente."""
    assert is_useful_payload({"name": "Produto", "current_price": "0"}) is True


@pytest.mark.parametrize("price_val", ["99.90", 99.90, 0, "R$ 50,00"])
def test_various_price_types_accepted(price_val):
    """is_useful_payload não converte preço — apenas verifica presença."""
    assert is_useful_payload({"name": "Item", "current_price": price_val}) is True
