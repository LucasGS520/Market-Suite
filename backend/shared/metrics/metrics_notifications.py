""" Métricas Prometheus para fluxos de notificações e alertas. """

from prometheus_client import Counter, Histogram


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

NOTIFICATION_DISPATCH_TOTAL = Counter(
    "notification_dispatch_total",
    "Total de notificações despachadas por canal e status",
    ["channel", "status"],
)

NOTIFICATION_ATTEMPTS_TOTAL = Counter(
    "notification_attempts_total",  
    "Total de tentativas de envio por canal e resultado",
    ["channel", "outcome"],
)

NOTIFICATIONS_SENT_TOTAL = Counter(
    "notifications_sent_total",
    "Total de notificações enviadas com sucesso",
    ["channel"],
)

NOTIFICATIONS_FAILED_TOTAL = Counter(
    "notifications_failed_total",
    "Total de notificações com falha permanente",
    ["channel", "reason"],
)

NOTIFICATIONS_RETRIED_TOTAL = Counter(
    "notifications_retried_total",
    "Total de notificações reenfileiradas para retry",
    ["channel"],
)

NOTIFICATIONS_DEDUPE_SKIPPED_TOTAL = Counter(
    "notifications_dedupe_skipped_total",
    "Total de notificações ignoradas por dedupe/cooldown",
    ["reason"],
)

NOTIFICATIONS_SEND_LATENCY_SECONDS = Histogram(
    "notifications_send_latency_seconds",
    "Latência de envio de notificações em segundos",
    ["channel", "outcome"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10),
)

__all__ = [
    "NOTIFICATION_EVENTS_TOTAL",
    "NOTIFICATION_ALERTS_CREATED_TOTAL",
    "NOTIFICATION_ALERTS_SKIPPED_TOTAL",
    "NOTIFICATION_IDEMPOTENCY_HITS_TOTAL",
    "NOTIFICATION_DISPATCH_TOTAL",
    "NOTIFICATION_ATTEMPTS_TOTAL",
    "NOTIFICATIONS_SENT_TOTAL",
    "NOTIFICATIONS_FAILED_TOTAL",
    "NOTIFICATIONS_RETRIED_TOTAL",
    "NOTIFICATIONS_DEDUPE_SKIPPED_TOTAL",
    "NOTIFICATIONS_SEND_LATENCY_SECONDS",
]
