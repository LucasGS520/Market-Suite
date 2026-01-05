""" Métricas Prometheus para fluxos de notificações e alertas. """

from prometheus_client import Counter


NOTIFICATION_EVENTS_TOTAL = Counter(
    "notification_events_total",
    "Total de eventos de domínio processados pela camada de notificações",
    ["event_type", "outcome"],
)

NOTIFICATION_ALERTS_CREATED_TOTAL = Counter(
    "notification_alerts_created_total",
    "Total de notificações criadas por tipo e canal",
    ["alert_type", "channel"],
)

NOTIFICATION_ALERTS_SKIPPED_TOTAL = Counter(
    "notification_alerts_skipped_total",
    "Total de alertas ignorados por regra ou cooldown",
    ["alert_type", "reason"],
)

NOTIFICATION_IDEMPOTENCY_HITS_TOTAL = Counter(
    "notification_idempotency_hits_total",
    "Total de eventos deduplicados por chave de idempotência",
    ["channel"],
)

__all__ = [
    "NOTIFICATION_EVENTS_TOTAL",
    "NOTIFICATION_ALERTS_CREATED_TOTAL",
    "NOTIFICATION_ALERTS_SKIPPED_TOTAL",
    "NOTIFICATION_IDEMPOTENCY_HITS_TOTAL",
]
