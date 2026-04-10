""" Testes unitários para o comparador de preços.

Cobre cenários de entrada vazia ou parcial que devem terminar de forma limpa
sem levantar exceções nem gerar resultados incoerentes.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from market_alert.enums.enums_products import ProductStatus
from market_alert.comparisons.utils.price_comparator import compare_prices
from market_alert.comparisons.utils.comparison_utils import filter_competitors_for_comparison


pytestmark = pytest.mark.unit


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_monitored(price: Decimal | None = Decimal("100.00")) -> Mock:
    m = Mock()
    m.id = uuid4()
    m.user_id = uuid4()
    m.current_price = price
    return m


def _make_competitor(
    price: Decimal | None = Decimal("90.00"),
    *,
    status: ProductStatus = ProductStatus.available,
    availability: bool | None = True,
    is_paused: bool = False,
) -> Mock:
    c = Mock()
    c.id = uuid4()
    c.name_competitor = "Loja Teste"
    c.current_price = price
    c.status = status
    c.availability = availability
    c.is_paused = is_paused
    c.last_checked = None
    return c


# ──────────────────────────────────────────────────────────────────────────────
# compare_prices — cenários de entrada vazia ou parcial
# ──────────────────────────────────────────────────────────────────────────────


def test_compare_prices_empty_competitors_returns_clean_result() -> None:
    """Lista vazia de concorrentes retorna resultado vazio sem exception."""
    monitored = _make_monitored()
    result = compare_prices(monitored, [])

    assert result["discrepancies"] == []
    assert result["lowest_competitor"] is None
    assert result["highest_competitor"] is None
    assert result["average_competitor_price"] is None
    assert result["monitored_price"] == Decimal("100.00")


def test_compare_prices_all_competitors_without_price_returns_clean_result() -> None:
    """Todos os concorrentes com current_price=None → fluxo termina limpo.

    Garante que compare_prices() filtra os sem preço internamente e não
    levanta KeyError/TypeError durante a criação de discrepâncias.
    """
    monitored = _make_monitored()
    c1 = _make_competitor(price=None)
    c2 = _make_competitor(price=None)

    result = compare_prices(monitored, [c1, c2])

    assert result["discrepancies"] == []
    assert result["lowest_competitor"] is None
    assert result["highest_competitor"] is None
    assert result["average_competitor_price"] is None


def test_compare_prices_single_valid_competitor_lowest_equals_highest() -> None:
    """Único concorrente válido → lowest_competitor e highest_competitor apontam para ele."""
    monitored = _make_monitored(Decimal("100.00"))
    c1 = _make_competitor(Decimal("85.00"))

    result = compare_prices(monitored, [c1])

    assert result["lowest_competitor"] is not None
    assert result["highest_competitor"] is not None
    assert result["lowest_competitor"]["competitor_id"] == str(c1.id)
    assert result["highest_competitor"]["competitor_id"] == str(c1.id)
    assert len(result["discrepancies"]) == 1


def test_compare_prices_excludes_unavailable_competitor() -> None:
    """Concorrente com availability=False deve ser excluído do cálculo."""
    monitored = _make_monitored(Decimal("100.00"))
    valid = _make_competitor(Decimal("80.00"), availability=True)
    unavailable = _make_competitor(Decimal("70.00"), availability=False)

    result = compare_prices(monitored, [valid, unavailable])

    assert len(result["discrepancies"]) == 1
    assert result["lowest_competitor"]["competitor_id"] == str(valid.id)


# ──────────────────────────────────────────────────────────────────────────────
# filter_competitors_for_comparison — filtragem por preço ausente
# ──────────────────────────────────────────────────────────────────────────────


def test_filter_competitors_excludes_all_when_no_price_available() -> None:
    """Concorrentes sem current_price nem histórico → entries vazio, razão missing_price."""
    db = Mock()
    c1 = _make_competitor(price=None)
    c2 = _make_competitor(price=None)

    with patch(
        "market_alert.comparisons.utils.comparison_utils.get_latest_price_for_competitor",
        return_value=None,
    ):
        filtered = filter_competitors_for_comparison(db, [c1, c2])

    assert filtered.entries == []
    assert filtered.filtered_reasons.get("missing_price", 0) == 2
