""" Pacote de agendamento compartilhado — política de cadência sem I/O ou ORM.

Importável por qualquer módulo da suite (market_alert, market_orchestrator)
sem criar dependências circulares.

Uso:

    from shared.scheduling import SchedulingContext, calculate_schedule, EVENT_STANDARD

    ctx = SchedulingContext(status="active", ...)
    decision = calculate_schedule(ctx, event_type=EVENT_STANDARD)
"""

from shared.scheduling.context import SchedulingContext
from shared.scheduling.scheduler import (
    STABILITY_UNSTABLE,
    STABILITY_STABLE,
    STABILITY_VERY_STABLE,
    EVENT_STANDARD,
    EVENT_PRICE_CHANGED,
    EVENT_AVAILABILITY_CHANGED,
    EVENT_NOT_MODIFIED,
    EVENT_RESUMED,
    EVENT_RETRY,
    RetryContext,
    SchedulingDecision,
    calculate_stability_score,
    calculate_next_interval,
    calculate_next_check_at,
    calculate_schedule,
    _utc_now,
    _parse_next_retry_at,
)

__all__ = [
    "SchedulingContext",
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
