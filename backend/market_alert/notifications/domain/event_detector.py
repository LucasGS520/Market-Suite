""" Detecção de eventos e mapeamento para tipos de alerta.

Funções puras — sem I/O, sem efeitos colaterais.
"""

from __future__ import annotations

from typing import Any

from market_alert.enums.enums_notifications import AlertType, EventType


def detect_events_from_snapshots(
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
) -> list[EventType]:
    """ Determina os eventos ocorridos a partir de mudanças nos snapshots.

    Compara os campos relevantes entre o snapshot anterior e o atual para
    identificar quais tipos de evento devem ser gerados.

    Args:
        previous_snapshot: Snapshot anterior (pode ser None para primeiro registro).
        current_snapshot: Snapshot atual com os dados mais recentes.

    Returns:
        Lista de EventType detectados. Pode ser vazia se não houve mudança.
    """
    previous = previous_snapshot or {}
    event_types: list[EventType] = []

    previous_price = previous.get("price")
    current_price = current_snapshot.get("price")
    if previous_price is not None and current_price is not None and previous_price != current_price:
        event_types.append(EventType.price_change)

    previous_availability = previous.get("availability")
    current_availability = current_snapshot.get("availability")
    if (
        previous_availability is not None
        and current_availability is not None
        and previous_availability != current_availability
    ):
        event_types.append(EventType.availability_change)

    if current_snapshot.get("competitor_important"):
        event_types.append(EventType.custom)

    return event_types

def map_event_to_alert_type(event_type: EventType) -> AlertType | None:
    """ Mapeia um tipo de evento para o tipo de alerta correspondente.

    Args:
        event_type: Tipo de evento detectado.

    Returns:
        AlertType correspondente, ou None se não houver mapeamento.
    """
    mapping = {
        EventType.price_change: AlertType.price_change,
        EventType.availability_change: AlertType.availability_change,
        EventType.scraping_error: AlertType.scraping_error,
        EventType.custom: AlertType.custom,
    }
    return mapping.get(event_type)
