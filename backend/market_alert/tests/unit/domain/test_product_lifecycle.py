"""Testes unitários da camada de domínio do ciclo de vida de produtos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_alert.domain.product_lifecycle import (
    compute_next_check_at,
    resolve_scheduling_event,
    update_competitor_price_change_tracking,
    update_price_change_tracking,
    validate_status_transition,
)
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.products.utils.interval_calculator_products import (
    EVENT_AVAILABILITY_CHANGED,
    EVENT_PRICE_CHANGED,
    EVENT_STANDARD,
    RetryContext,
)


def test_resolve_scheduling_event_prioriza_mudanca_de_preco() -> None:
    """Garante precedência de preço quando múltiplos sinais mudam juntos."""
    assert resolve_scheduling_event(price_changed=True, availability_changed=True) == EVENT_PRICE_CHANGED
    assert resolve_scheduling_event(price_changed=False, availability_changed=True) == EVENT_AVAILABILITY_CHANGED
    assert resolve_scheduling_event(price_changed=False, availability_changed=False) == EVENT_STANDARD


def test_validate_status_transition_aplica_matriz_de_transicoes() -> None:
    """Valida transições permitidas e bloqueadas pela regra de domínio."""
    assert validate_status_transition(MonitoredStatus.pending, MonitoredStatus.active)
    assert not validate_status_transition(MonitoredStatus.failed, MonitoredStatus.active)


def test_compute_next_check_at_com_retry_context_respeita_cooldown(monitored) -> None:
    """Confirma que eventos de retry retornam decisão com horário futuro."""
    reference = datetime.now(timezone.utc)
    retry_context = RetryContext(reason="429", next_retry_at=reference + timedelta(minutes=10))

    decision = compute_next_check_at(
        monitored,
        reference_time=reference,
        event_type=EVENT_STANDARD,
        retry_context=retry_context,
    )

    assert decision.next_check_at >= retry_context.next_retry_at
    assert decision.interval_seconds >= 0


def test_update_price_change_tracking_atualiza_campos_quando_preco_muda(monitored) -> None:
    """Assegura reset de estabilidade e marcação de coleta em mudança real."""
    collected_at = datetime.now(timezone.utc)
    monitored.stability_score = 2

    update_price_change_tracking(
        monitored,
        new_price=Decimal("120.00"),
        old_price=Decimal("100.00"),
        collected_at=collected_at,
    )

    assert monitored.last_price_change_at == collected_at
    assert monitored.group_collected_at == collected_at
    assert monitored.stability_score == 0


def test_update_competitor_price_change_tracking_so_marca_em_mudanca(competitor) -> None:
    """Evita falsa mudança quando valor coletado permanece igual."""
    collected_at = datetime.now(timezone.utc)
    update_competitor_price_change_tracking(
        competitor,
        new_price=Decimal("99.00"),
        old_price=Decimal("99.00"),
        collected_at=collected_at,
    )
    assert competitor.last_price_change_at is None
    