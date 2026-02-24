""" Resolução de prioridade de notificação com base em regras de alerta.

Funções puras — sem I/O, sem efeitos colaterais.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market_alert.models import AlertRule


def resolve_priority(alert_rule: "AlertRule | None") -> int:
    """ Define a prioridade da notificação com base na configuração da regra de alerta.

    A prioridade é lida do campo `rule_config` da regra, se disponível.
    Valores maiores indicam maior prioridade.

    Args:
        alert_rule: Regra de alerta associada à notificação (pode ser None).

    Returns:
        Inteiro representando a prioridade. 0 é o valor padrão (menor prioridade).
    """
    if alert_rule and isinstance(alert_rule.rule_config, dict):
        priority = alert_rule.rule_config.get("priority")
        if isinstance(priority, int):
            return priority
    return 0
