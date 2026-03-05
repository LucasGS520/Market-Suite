""" Validação de contrato de snapshot para o fluxo de notificações.

Funções puras — sem I/O, sem logging, sem efeitos colaterais.
Retornam (bool, list[str]) para que o chamador decida como reagir.
"""

from __future__ import annotations

from typing import Any


def validate_snapshot_contract(
    snapshot: dict[str, Any],
) -> tuple[bool, list[str]]:
    """ Valida que um snapshot respeita o contrato mínimo esperado.

    Contrato de snapshot:
    - Deve ser um dicionário (não None, não lista, não string)
    - Campos opcionais com tipos esperados (todos acessados via .get()):
      - price: float | str | None
      - availability: bool | None
      - summary: dict | None
      - price_delta_percent: float | None

    Returns:
        Tupla (válido, lista de erros). Se válido=True, erros é lista vazia.
    """
    if not isinstance(snapshot, dict):
        return False, [f"esperado dict, recebido {type(snapshot).__name__}"]

    errors: list[str] = []

    summary = snapshot.get("summary")
    if summary is not None and not isinstance(summary, dict):
        errors.append(f"summary esperado dict, recebido {type(summary).__name__}")

    availability = snapshot.get("availability")
    if availability is not None and not isinstance(availability, bool):
        errors.append(f"availability esperado bool, recebido {type(availability).__name__}")

    return len(errors) == 0, errors
