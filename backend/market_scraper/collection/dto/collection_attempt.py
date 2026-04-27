""" DTO imutável para uma tentativa individual de coleta de HTML. """

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionAttempt:
    """ Registro de uma única tentativa de aquisição de HTML.

    Attributes:
        layer: Camada usada — ``"http"`` ou ``"browser"``.
        status: Resultado — ``"success"``, ``"failure"`` ou ``"escalated"``.
        error_code: Código canônico do erro, ou ``None`` em sucesso.
        duration_ms: Duração da tentativa em milissegundos.
        reason: Razão do resultado vinda da política de classificação.
    """

    layer: str
    status: str
    error_code: str | None
    duration_ms: float
    reason: str | None


__all__ = ["CollectionAttempt"]
