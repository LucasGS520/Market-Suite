""" Métricas que acompanham regras e disparos de alertas """

from prometheus_client import Counter, Gauge

ALERT_RULES_TRIGGERED_TOTAL = Counter(
    "alert_rules_triggered_total",
    "Total de vezes que uma regra de alerta foi acionada",
    ["rule_type"],
)

ALERT_RULES_SUPPRESSED_TOTAL = Counter(
    "alert_rules_suppressed_total",
    "Alertas suprimidos por cooldown ou duplicidade",
    ["reason"],
)

ALERT_RULES_ACTIVE = Gauge(
    "alert_rules_active",
    "Número de regras de alerta ativas no sistema",
)

__all__ = [
    "ALERT_RULES_TRIGGERED_TOTAL",
    "ALERT_RULES_SUPPRESSED_TOTAL",
    "ALERT_RULES_ACTIVE"
]
