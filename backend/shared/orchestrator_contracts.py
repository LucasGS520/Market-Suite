"""Factory methods para criação de DTOs da comunicação Temporal ↔ market_alert.

Abstração que centraliza a construção de payloads tipados para o orquestrador.
Nenhuma dependência de market_alert, market_orchestrator ou infra.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from shared.schemas.shared_schemas_orchestrator import (
    CollectionPayload,
    CollectionResult,
    DispatchActivityOutput,
)


def create_collection_payload(
    monitored_id: UUID | str,
    user_id: UUID | str,
    url: str,
    kind: str = "monitored",
    *,
    trace_id: str | None = None,
    force_compare: bool = False,
    competitor_id: UUID | str | None = None,
    name: str | None = None,
) -> CollectionPayload:
    """Constrói CollectionPayload tipado com defaults seguros.

    Args:
        monitored_id: UUID do produto monitorado raiz.
        user_id: UUID do usuário dono.
        url: URL a ser coletada.
        kind: 'monitored' ou 'competitor'.
        trace_id: ID de rastreamento; gerado automaticamente se ausente.
        force_compare: força recomputação de comparação após coleta.
        competitor_id: UUID do concorrente (obrigatório se kind='competitor').
        name: nome para logs.
    """
    return CollectionPayload(
        kind=kind,  # type: ignore[arg-type]
        monitored_id=UUID(str(monitored_id)),
        user_id=UUID(str(user_id)),
        url=url,
        trace_id=trace_id or str(uuid4()),
        force_compare="true" if force_compare else None,
        competitor_id=UUID(str(competitor_id)) if competitor_id else None,
        name=name,
    )


def build_activity_result(
    success: bool,
    monitored_id: UUID | str,
    *,
    trace_id: str = "",
    error: str | None = None,
    collected_at: str | None = None,
) -> CollectionResult:
    """Constrói CollectionResult para retorno de activities.

    Args:
        success: se a coleta/operação foi bem-sucedida.
        monitored_id: UUID do produto monitorado.
        trace_id: ID de rastreamento da operação.
        error: mensagem de erro em caso de falha.
        collected_at: ISO timestamp da coleta concluída.
    """
    return CollectionResult(
        success=success,
        monitored_id=UUID(str(monitored_id)),
        trace_id=trace_id,
        error=error,
        collected_at=collected_at,
    )


def build_dispatch_output(
    success: bool,
    *,
    task_id: str | None = None,
    error: str | None = None,
) -> DispatchActivityOutput:
    """Constrói DispatchActivityOutput padronizado."""
    return DispatchActivityOutput(success=success, task_id=task_id, error=error)


__all__ = [
    "create_collection_payload",
    "build_activity_result",
    "build_dispatch_output",
]
