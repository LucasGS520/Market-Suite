""" Política central de agendamento de monitorados — lógica pura sem I/O.

Este módulo concentra toda a decisão de ``next_check_at`` para evitar regras
espalhadas entre CRUD, serviços e orquestrador. A API principal é
:func:`calculate_schedule`, que produz uma decisão explicável com estabilidade,
intervalo e motivo aplicado.

Não possui dependências de ``market_alert`` — consome apenas ``shared.core.config_base``
e ``shared.scheduling.context``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from shared.core.config_base import ConfigBase
from shared.scheduling.context import SchedulingContext


_cfg = ConfigBase()

STABILITY_UNSTABLE = 0
STABILITY_STABLE = 1
STABILITY_VERY_STABLE = 2

EVENT_STANDARD = "standard"
EVENT_PRICE_CHANGED = "price_changed"
EVENT_AVAILABILITY_CHANGED = "availability_changed"
EVENT_NOT_MODIFIED = "not_modified"
EVENT_RESUMED = "resumed"
EVENT_RETRY = "retry"

_COOLDOWN_REASONS = {"rate_limit", "too_many_requests", "429", "temporary_failure"}
_TRANSITION_EVENTS = {EVENT_PRICE_CHANGED, EVENT_AVAILABILITY_CHANGED, EVENT_RESUMED}
_STATUS_PENDING = "pending"


@dataclass(frozen=True)
class RetryContext:
    """ Contexto opcional de retry para impor cooldown mínimo.

    Attributes:
        reason: Motivo do retry usado para decidir se aplica cooldown.
        next_retry_at: Horário sugerido por fluxos de erro/transiente.
    """
    reason: str | None = None
    next_retry_at: datetime | None = None

@dataclass(frozen=True)
class SchedulingDecision:
    """ Resultado imutável da política de agendamento centralizada.

    Attributes:
        stability_score: Score de estabilidade (0 instável, 1 estável, 2 muito estável).
        next_check_at: Próximo horário definitivo para reenfileirar o monitorado.
        interval_seconds: Distância entre ``reference_time`` e ``next_check_at``.
        reason: Explicação curta da regra aplicada para auditoria em logs.
    """
    stability_score: int
    next_check_at: datetime
    interval_seconds: int
    reason: str

def _utc_now() -> datetime:
    """ Retorna timestamp em UTC sem microssegundos para logs """
    return datetime.now(timezone.utc).replace(microsecond=0)

def _normalize_datetime(value: datetime | None) -> datetime | None:
    """ Normaliza datas para UTC preservando valores nulos """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def _parse_next_retry_at(value: str | None) -> datetime | None:
    """ Converte string ISO de retry para datetime com timezone """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _random_interval(min_seconds: int, max_seconds: int) -> int:
    """ Sorteia um intervalo entre limites incluindo as extremidades """
    if min_seconds >= max_seconds:
        return min_seconds
    return random.randint(min_seconds, max_seconds)

def calculate_stability_score(
    ctx: SchedulingContext,
    *,
    reference_time: datetime | None = None,
) -> int:
    """ Calcula pontuação de estabilidade baseada na última mudança registrada """
    now = _normalize_datetime(reference_time) or datetime.now(timezone.utc)

    #Prioriza mudanças explícitas, mas considera indicadores de grupo e criação como fallback
    last_change = (
        ctx.last_price_change_at
        or ctx.group_collected_at
        or ctx.last_scraped_at
        or ctx.created_at
    )
    last_change = _normalize_datetime(last_change)

    if last_change is None:
        return STABILITY_UNSTABLE

    days_since_change = (now - last_change).total_seconds() / 86400

    if days_since_change >= _cfg.STABILITY_DAYS_VERY_STABLE:
        return STABILITY_VERY_STABLE
    if days_since_change >= _cfg.STABILITY_DAYS_STABLE:
        return STABILITY_STABLE
    return STABILITY_UNSTABLE

def _interval_window_from_stability(stability_score: int) -> tuple[int, int, str]:
    """ Retorna janela (min, max) e motivo associado à estabilidade informada """
    if stability_score == STABILITY_VERY_STABLE:
        return (
            _cfg.COLLECT_INTERVAL_VERY_STABLE_MIN,
            _cfg.COLLECT_INTERVAL_VERY_STABLE_MAX,
            "stability_very_stable",
        )

    if stability_score == STABILITY_STABLE:
        return (
            _cfg.COLLECT_INTERVAL_STABLE_MIN,
            _cfg.COLLECT_INTERVAL_STABLE_MAX,
            "stability_stable",
        )

    return (
        _cfg.COLLECT_INTERVAL_UNSTABLE_MIN,
        _cfg.COLLECT_INTERVAL_UNSTABLE_MAX,
        "stability_unstable",
    )

def _resolve_retry_candidate(
    *,
    reference_time: datetime,
    retry_context: RetryContext | None,
) -> tuple[datetime | None, str | None]:
    """ Resolve horário mínimo de retry para erros transitórios e rate-limit

    O cálculo respeita ``next_retry_at`` quando já vier do fluxo de coleta e,
    para motivos sensíveis, aplica cooldown mínimo configurável.
    """
    if retry_context is None:
        return None, None

    retry_reason = (retry_context.reason or "").strip().lower()
    parsed_retry_at = _normalize_datetime(retry_context.next_retry_at)
    if parsed_retry_at and parsed_retry_at < reference_time:
        parsed_retry_at = reference_time

    if retry_reason not in _COOLDOWN_REASONS:
        return parsed_retry_at, None

    cooldown_floor = reference_time + timedelta(seconds=_cfg.SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS)
    if parsed_retry_at is None or parsed_retry_at < cooldown_floor:
        return cooldown_floor, "retry_cooldown_floor"
    return parsed_retry_at, "retry_payload_respected"

def calculate_next_interval(
    ctx: SchedulingContext,
    *,
    reference_time: datetime | None = None,
) -> int:
    """ Retorna intervalo aleatório para o próximo ciclo conforme estabilidade """
    normalized_reference = _normalize_datetime(reference_time) or datetime.now(timezone.utc)
    stability_score = calculate_stability_score(ctx, reference_time=normalized_reference)
    min_seconds, max_seconds, _ = _interval_window_from_stability(stability_score)
    return _random_interval(min_seconds, max_seconds)

def calculate_schedule(
    ctx: SchedulingContext,
    *,
    reference_time: datetime | None = None,
    event_type: str = EVENT_STANDARD,
    retry_context: RetryContext | None = None,
) -> SchedulingDecision:
    """ Calcula decisão completa de agendamento em um único ponto.

    Args:
        ctx: Estado do monitorado necessário para a decisão.
        reference_time: Tempo-base do cálculo (ex.: coleta finalizada).
        event_type: Tipo de evento que disparou o cálculo.
        retry_context: Contexto opcional para fluxos de retry/cooldown.

    Returns:
        SchedulingDecision: Decisão final com score, intervalo e motivo.
    """
    normalized_reference = _normalize_datetime(reference_time) or datetime.now(timezone.utc)

    if ctx.status == _STATUS_PENDING and not ctx.last_checked:
        #Mantém primeira coleta imediata para itens recém-criados em estado pendente
        return SchedulingDecision(
            stability_score=STABILITY_UNSTABLE,
            next_check_at=normalized_reference,
            interval_seconds=0,
            reason="initial_pending_immediate",
        )

    transition_event = event_type in _TRANSITION_EVENTS
    if transition_event:
        #Mudanças relevantes reduzem estabilidade para acelerar convergência
        stability_score = STABILITY_UNSTABLE
    else:
        stability_score = calculate_stability_score(ctx, reference_time=normalized_reference)

    min_seconds, max_seconds, window_reason = _interval_window_from_stability(stability_score)
    sampled_interval = _random_interval(min_seconds, max_seconds)
    candidate_next_check_at = normalized_reference + timedelta(seconds=sampled_interval)
    reason = window_reason if not transition_event else f"transition_{event_type}"

    retry_candidate, retry_reason = _resolve_retry_candidate(
        reference_time=normalized_reference,
        retry_context=retry_context,
    )
    if retry_candidate and retry_candidate > candidate_next_check_at:
        candidate_next_check_at = retry_candidate
        reason = retry_reason or reason

    interval_seconds = max(0, int((candidate_next_check_at - normalized_reference).total_seconds()))
    return SchedulingDecision(
        stability_score=stability_score,
        next_check_at=candidate_next_check_at,
        interval_seconds=interval_seconds,
        reason=reason,
    )

def calculate_next_check_at(
    ctx: SchedulingContext,
    collected_at: datetime | None,
) -> datetime:
    """ Mantém API legada retornando apenas o datetime da próxima coleta """
    decision = calculate_schedule(
        ctx,
        reference_time=collected_at,
        event_type=EVENT_STANDARD,
    )
    return decision.next_check_at


__all__ = [
    "STABILITY_UNSTABLE",
    "STABILITY_STABLE",
    "STABILITY_VERY_STABLE",
    "EVENT_STANDARD",
    "EVENT_PRICE_CHANGED",
    "EVENT_AVAILABILITY_CHANGED",
    "EVENT_NOT_MODIFIED",
    "EVENT_RESUMED",
    "EVENT_RETRY",
    "RetryContext",
    "SchedulingDecision",
    "calculate_stability_score",
    "calculate_next_interval",
    "calculate_next_check_at",
    "calculate_schedule",
    "_utc_now",
    "_parse_next_retry_at",
]
