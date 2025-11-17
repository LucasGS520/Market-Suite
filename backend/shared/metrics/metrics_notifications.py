""" Métricas sobre envio, supressão e conexão do canal de notificações """

from prometheus_client import Counter, Histogram

NOTIFICATIONS_SENT_TOTAL = Counter(
    "notifications_sent_total",
    "Total de notificações enviadas",
    ["channel", "success"],
)

NOTIFICATIONS_SKIPPED_TOTAL = Counter(
    "notifications_skipped_total",
    "Total de notificações não enviadas",
    ["reason"],
)

NOTIFICATIONS_WS_REJECTED_TOTAL = Counter(
    "notifications_ws_rejected_total",
    "Total de conexões WebSocket de notificações rejeitadas",
    ["reason"],
)

NOTIFICATION_SEND_DURATION_SECONDS = Histogram(
    "notification_send_duration_seconds",
    "Tempo de envio de notificações (segundos)",
    ["channel"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0],
)

__all__ = [
    "NOTIFICATIONS_SENT_TOTAL",
    "NOTIFICATIONS_SKIPPED_TOTAL",
    "NOTIFICATIONS_WS_REJECTED_TOTAL",
    "NOTIFICATION_SEND_DURATION_SECONDS",
]
