""" Testes de contrato para a política central de agendamento de monitorados. """

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from market_alert.enums.enums_products import MonitoredStatus
from market_alert.utils import interval_calculator_products as schedule_utils


def _build_product(
    *,
    last_change_at: datetime,
    status: MonitoredStatus = MonitoredStatus.active,
    last_checked: datetime | None = None,
):
    """ Cria monitorado mínimo para validar política sem depender de banco real. """
    return SimpleNamespace(
        last_price_change_at=last_change_at,
        group_collected_at=last_change_at,
        last_scraped_at=last_change_at,
        created_at=last_change_at,
        status=status,
        last_checked=last_checked,
        next_check_at=None,
    )


@pytest.mark.parametrize(
    ("days_since_change", "expected_stability", "expected_min", "expected_max"),
    [
        (1, schedule_utils.STABILITY_UNSTABLE, 300, 600),
        (5, schedule_utils.STABILITY_STABLE, 600, 900),
        (10, schedule_utils.STABILITY_VERY_STABLE, 900, 1200),
    ],
)
def test_calculate_schedule_respeita_janela_por_estabilidade(
    monkeypatch,
    days_since_change: int,
    expected_stability: int,
    expected_min: int,
    expected_max: int,
) -> None:
    """ Garante limites de janela para cada nível de estabilidade. """
    reference = datetime(2026, 1, 15, tzinfo=timezone.utc)
    product = _build_product(last_change_at=reference - timedelta(days=days_since_change))

    monkeypatch.setattr(schedule_utils.settings, "STABILITY_DAYS_STABLE", 3)
    monkeypatch.setattr(schedule_utils.settings, "STABILITY_DAYS_VERY_STABLE", 7)
    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_UNSTABLE_MIN", 300)
    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_UNSTABLE_MAX", 600)
    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_STABLE_MIN", 600)
    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_STABLE_MAX", 900)
    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_VERY_STABLE_MIN", 900)
    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_VERY_STABLE_MAX", 1200)
    monkeypatch.setattr(schedule_utils.random, "randint", lambda low, high: high)

    decision = schedule_utils.calculate_schedule(
        product,
        reference_time=reference,
        event_type=schedule_utils.EVENT_STANDARD,
    )

    assert decision.stability_score == expected_stability
    assert expected_min <= decision.interval_seconds <= expected_max
    assert decision.next_check_at == reference + timedelta(seconds=expected_max)


@pytest.mark.parametrize(
    "event_type",
    [schedule_utils.EVENT_PRICE_CHANGED, schedule_utils.EVENT_AVAILABILITY_CHANGED, schedule_utils.EVENT_RESUMED],
)
def test_calculate_schedule_forca_instabilidade_em_transicoes(monkeypatch, event_type: str) -> None:
    """ Eventos de transição devem retornar para janela instável imediatamente. """
    reference = datetime(2026, 2, 1, tzinfo=timezone.utc)
    product = _build_product(last_change_at=reference - timedelta(days=30))

    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_UNSTABLE_MIN", 120)
    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_UNSTABLE_MAX", 120)

    decision = schedule_utils.calculate_schedule(
        product,
        reference_time=reference,
        event_type=event_type,
    )

    assert decision.stability_score == schedule_utils.STABILITY_UNSTABLE
    assert decision.interval_seconds == 120
    assert decision.reason == f"transition_{event_type}"


def test_calculate_schedule_aplica_cooldown_minimo_para_retry(monkeypatch) -> None:
    """ Retry por rate-limit respeita piso mínimo mesmo com next_retry_at menor. """
    reference = datetime(2026, 3, 1, tzinfo=timezone.utc)
    product = _build_product(last_change_at=reference - timedelta(days=1))

    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_UNSTABLE_MIN", 120)
    monkeypatch.setattr(schedule_utils.settings, "COLLECT_INTERVAL_UNSTABLE_MAX", 120)
    monkeypatch.setattr(schedule_utils.settings, "SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS", 600)

    decision = schedule_utils.calculate_schedule(
        product,
        reference_time=reference,
        event_type=schedule_utils.EVENT_RETRY,
        retry_context=schedule_utils.RetryContext(
            reason="rate_limit",
            next_retry_at=reference + timedelta(seconds=60),
        ),
    )

    assert decision.interval_seconds == 600
    assert decision.reason == "retry_cooldown_floor"
    assert decision.next_check_at == reference + timedelta(seconds=600)


def test_calculate_schedule_mantem_primeira_coleta_pendente_imediata() -> None:
    """ Monitorado recém-criado pendente mantém execução imediata. """
    reference = datetime(2026, 3, 2, tzinfo=timezone.utc)
    product = _build_product(
        last_change_at=reference,
        status=MonitoredStatus.pending,
        last_checked=None,
    )

    decision = schedule_utils.calculate_schedule(
        product,
        reference_time=reference,
        event_type=schedule_utils.EVENT_STANDARD,
    )

    assert decision.interval_seconds == 0
    assert decision.next_check_at == reference
    assert decision.reason == "initial_pending_immediate"
    