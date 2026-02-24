""" Resolução de cooldown para controle de frequência de notificações.

Funções puras — sem I/O, sem efeitos colaterais.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market_alert.models import AlertRule, UserNotificationPreference


def resolve_cooldown_seconds(
    *,
    preference: "UserNotificationPreference | None",
    alert_rule: "AlertRule | None",
    default_cooldown_seconds: int,
) -> int:
    """ Resolve o cooldown final com base em regra de alerta, preferência ou default.

    Prioridade:
    1. Cooldown da regra de alerta (mais específica)
    2. Cooldown da preferência do usuário
    3. Default fornecido pelo chamador (vem das settings)

    Args:
        preference: Preferência de notificação do usuário.
        alert_rule: Regra de alerta configurada.
        default_cooldown_seconds: Valor padrão quando não há configuração específica.

    Returns:
        Número de segundos de cooldown a aplicar.
    """
    if alert_rule and alert_rule.cooldown_seconds:
        return alert_rule.cooldown_seconds
    if preference and preference.cooldown_seconds:
        return preference.cooldown_seconds
    return default_cooldown_seconds

def is_within_cooldown(
    last_sent_at: datetime | None,
    cooldown_seconds: int,
    *,
    now: datetime,
) -> bool:
    """ Verifica se o cooldown ainda está ativo com base no último envio.

    Args:
        last_sent_at: Data/hora do último envio bem-sucedido.
        cooldown_seconds: Duração do cooldown em segundos.
        now: Instante de referência para o cálculo.

    Returns:
        True se ainda está dentro do período de cooldown (deve suprimir).
        False se o cooldown expirou ou não estava ativo.
    """
    if last_sent_at is None or cooldown_seconds <= 0:
        return False
    elapsed = (now - last_sent_at).total_seconds()
    return elapsed < cooldown_seconds
