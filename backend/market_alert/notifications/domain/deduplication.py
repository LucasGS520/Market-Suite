""" Geração de hash de deduplicação para notificações idempotentes.

Funções puras — sem I/O, sem efeitos colaterais.
"""

from __future__ import annotations

from hashlib import sha256

from market_alert.enums.enums_notifications import EventType


def generate_dedup_hash(
    *,
    user_id: str,
    monitored_id: str,
    event_type: EventType,
) -> str:
    """ Gera um hash determinístico para identificar notificações equivalentes.

    O hash é baseado nos três identificadores que definem a unicidade de uma
    notificação: o usuário, o produto monitorado e o tipo de evento.

    Args:
        user_id: ID do usuário (como string).
        monitored_id: ID do produto monitorado (como string).
        event_type: Tipo do evento que gerou a notificação.

    Returns:
        String hexadecimal SHA-256 de 64 caracteres.
    """
    raw = f"{user_id}:{monitored_id}:{event_type.value}"
    return sha256(raw.encode("utf-8")).hexdigest()
