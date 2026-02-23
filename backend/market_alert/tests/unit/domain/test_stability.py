"""Testes unitários para cálculo de estabilidade no domínio."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_alert.domain.stability import (
    STABILITY_STABLE,
    STABILITY_UNSTABLE,
    STABILITY_VERY_STABLE,
    calculate_stability_score,
)


def test_calculate_stability_score_unstable_para_mudanca_recente(monitored) -> None:
    """Pontuação deve permanecer instável quando houve mudança recente."""
    monitored.last_price_change_at = datetime.now(timezone.utc) - timedelta(hours=2)
    score = calculate_stability_score(monitored, reference_time=datetime.now(timezone.utc))
    assert score == STABILITY_UNSTABLE


def test_calculate_stability_score_usa_created_at_como_fallback(monitored) -> None:
    """Quando não há histórico de mudança, usa created_at como referência."""
    reference = datetime.now(timezone.utc)
    monitored.last_price_change_at = None
    monitored.group_collected_at = None
    monitored.last_scraped_at = None
    monitored.created_at = reference - timedelta(days=30)

    score = calculate_stability_score(monitored, reference_time=reference)
    assert score in {STABILITY_STABLE, STABILITY_VERY_STABLE}
    