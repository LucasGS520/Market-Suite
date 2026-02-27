""" Módulos de domínio puro para notificações — sem I/O, sem efeitos colaterais 

Reexporta funções determinísticas (sem I/O) para facilitar importações e
deixar explícito o contrato público de regras de negócio.
"""

from market_alert.notifications.domain.channel_resolver import (
    is_channel_confirmed,
    resolve_channel_destination,
)
from market_alert.notifications.domain.cooldown_resolver import (
    is_within_cooldown,
    resolve_cooldown_seconds,
)
from market_alert.notifications.domain.deduplication import generate_dedup_hash
from market_alert.notifications.domain.event_detector import (
    detect_events_from_snapshots,
    map_event_to_alert_type,
)
from market_alert.notifications.domain.price_calculator import (
    calculate_price_delta_percent,
    is_delta_below_threshold,
)
from market_alert.notifications.domain.priority_resolver import resolve_priority
from market_alert.notifications.domain.snapshot_validator import validate_snapshot_contract

__all__ = [
    "resolve_channel_destination",
    "is_channel_confirmed",
    "resolve_cooldown_seconds",
    "is_within_cooldown",
    "generate_dedup_hash",
    "detect_events_from_snapshots",
    "map_event_to_alert_type",
    "calculate_price_delta_percent",
    "is_delta_below_threshold",
    "resolve_priority",
    "validate_snapshot_contract",
]
