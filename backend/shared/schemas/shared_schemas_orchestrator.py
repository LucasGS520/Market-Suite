"""Tipos e DTOs para comunicação Temporal ↔ market_alert.

Contrato único entre orquestrador e domínio de negócio.
Nenhuma dependência de market_alert, market_orchestrator ou infra.
Apenas Pydantic, dataclasses e tipos primitivos.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


logger = logging.getLogger(__name__)


# ─────────────────────────── Payload de Coleta ────────────────────────────

class CollectionPayload(BaseModel):
    """Payload tipado para coletas de monitorados e concorrentes.

    Campos obrigatórios:
        kind: tipo da coleta — 'monitored' ou 'competitor'.
        monitored_id: UUID do produto monitorado raiz.
        url: URL a ser coletada pelo scraper.
        trace_id: identificador de rastreamento distribuído (sempre presente em formato UUID canônico).
        user_id: UUID do usuário dono do monitorado.

    Campos opcionais:
        version: versão do schema para compatibilidade futura (padrão: 1).
        competitor_id: UUID do concorrente quando kind='competitor'.
        enqueued_at: ISO timestamp de quando o item entrou na fila de prioridade.
        force_compare: flag para forçar recomputação de comparação após coleta.
        collected_at: ISO timestamp da coleta (preenchido pelo coletor após execução).
        name: nome de identificação usado em logs e depuração.
    """

    version: int = Field(default=1, description="Versão do schema de payload")
    kind: Literal["monitored", "competitor"] = Field(..., description="Tipo da coleta")
    monitored_id: UUID = Field(..., description="UUID do produto monitorado raiz")
    url: str = Field(..., description="URL a ser coletada")
    trace_id: str = Field(default="", description="ID de rastreamento distribuído")
    user_id: UUID = Field(..., description="UUID do usuário dono do monitorado")

    competitor_id: UUID | None = Field(default=None, description="UUID do concorrente (apenas para kind=competitor)")
    enqueued_at: str | None = Field(default=None, description="ISO timestamp de enfileiramento")
    force_compare: str | None = Field(default=None, description="Flag para forçar comparação ('true'/'1')")
    collected_at: str | None = Field(default=None, description="ISO timestamp da coleta")
    name: str | None = Field(default=None, description="Nome para logs e depuração")

    @model_validator(mode="before")
    @classmethod
    def _ensure_trace_id(cls, data: dict) -> dict:
        """Garante trace_id sempre preenchido — gera UUID se ausente ou vazio."""
        if isinstance(data, dict) and not data.get("trace_id"):
            data["trace_id"] = str(uuid4())
        return data

    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id_uuid_canonical(cls, trace_id: str) -> str:
        """Valida trace_id no formato UUID canônico."""
        normalized = trace_id.strip()
        try:
            parsed = UUID(normalized)
        except ValueError as exc:
            raise ValueError("trace_id deve estar no formato UUID canônico.") from exc
        canonical = str(parsed)
        if normalized != canonical:
            raise ValueError("trace_id deve estar no formato UUID canônico.")
        return canonical

    @model_validator(mode="after")
    def _validate_kind_specific_fields(self) -> CollectionPayload:
        """Aplica regras de consistência entre kind e campos específicos."""
        if self.kind == "competitor" and self.competitor_id is None:
            raise ValueError("competitor_id é obrigatório quando kind='competitor'.")
        if self.kind == "monitored" and self.competitor_id is not None:
            raise ValueError("competitor_id deve ser omitido quando kind='monitored'.")
        return self


def validate_payload(payload: dict | None) -> CollectionPayload:
    """Valida dicionário de payload retornando CollectionPayload tipado.

    Lança ValueError se o payload for None ou inválido.
    """
    if payload is None:
        raise ValueError("Payload de coleta não pode ser None")
    try:
        return CollectionPayload.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"Payload de coleta inválido: {exc}") from exc


# ──────────────────────────── DTOs de Activities ────────────────────────────

@dataclass
class DispatchActivityOutput:
    """Resultado da activity dispatch_collection."""
    success: bool = True
    task_id: str | None = None
    error: str | None = None


@dataclass
class QueryStatusOutput:
    """Resultado da activity query_collection_status."""
    completed: bool = False
    last_error: str | None = None


@dataclass
class PolicyActivityOutput:
    """Resultado da activity fetch_monitored_policy."""
    interval_seconds: int = 3600
    next_check_at: str | None = None
    paused: bool = False
    stability_score: int = 0
    scheduling_reason: str = "unknown"


@dataclass
class WorkflowStateSnapshot:
    """Snapshot genérico de estado do workflow (sem dependência de enums do orquestrador)."""
    state: str = "active"
    monitored_id: str = ""
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_error: str | None = None
    attempt_count: int = 0


class CollectionResult(BaseModel):
    """Resultado de uma coleta reportada pelo sistema."""
    success: bool
    monitored_id: UUID
    trace_id: str = ""
    error: str | None = None
    collected_at: str | None = None


__all__ = [
    "CollectionPayload",
    "validate_payload",
    "DispatchActivityOutput",
    "QueryStatusOutput",
    "PolicyActivityOutput",
    "WorkflowStateSnapshot",
    "CollectionResult",
]
