""" Tipos e DTOs para comunicação Temporal ↔ market_alert.

Contrato único entre orquestrador e domínio de negócio.
Nenhuma dependência de market_alert, market_orchestrator ou infra.
Apenas Pydantic, dataclasses e tipos primitivos.

---

## Regras de Compatibilidade Retroativa

Estes tipos cruzam fronteiras de serialização (fila Celery, Temporal,
Redis). Mudanças devem seguir estas regras para não quebrar execuções em voo:

1. **Apenas adições são seguras**: novos campos com `default` não quebram
   leitores antigos. Nunca remover ou renomear campo sem versionamento.
2. `schema_version` deve ser incrementado quando campos obrigatórios mudarem
   ou semântica de campos existentes for alterada de forma incompatível.
3. Readers devem tolerar campos desconhecidos (já garantido por Pydantic
   `extra="ignore"` e `dataclass` com `from_dict`).
4. Nunca recriar `CollectionPayload` ou qualquer DTO deste módulo em outro
   serviço — sempre importar daqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


logger = logging.getLogger(__name__)

# ─────────────────────────── Payload de Coleta ────────────────────────────

class CollectionPayload(BaseModel):
    """ Payload tipado para coletas de monitorados e concorrentes.

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
    correlation_id: str | None = Field(default=None, description="ID de correlação do ciclo de workflow (preenchido pelo orquestrador)")

    @model_validator(mode="before")
    @classmethod
    def _ensure_trace_id(cls, data: dict) -> dict:
        """ Garante trace_id sempre preenchido — gera UUID se ausente ou vazio."""
        if isinstance(data, dict) and not data.get("trace_id"):
            data["trace_id"] = str(uuid4())
        return data

    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id_uuid_canonical(cls, trace_id: str) -> str:
        """ Valida trace_id no formato UUID canônico."""
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
        """ Aplica regras de consistência entre kind e campos específicos."""
        if self.kind == "competitor" and self.competitor_id is None:
            raise ValueError("competitor_id é obrigatório quando kind='competitor'.")
        if self.kind == "monitored" and self.competitor_id is not None:
            raise ValueError("competitor_id deve ser omitido quando kind='monitored'.")
        return self

def validate_payload(payload: dict | None) -> CollectionPayload:
    """ Valida dicionário de payload retornando CollectionPayload tipado.

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
    """ Resultado da activity dispatch_collection."""
    success: bool = True
    task_id: str | None = None
    error: str | None = None
    schema_version: int = 1

@dataclass
class QueryStatusOutput:
    """ Resultado da activity query_collection_status."""
    completed: bool = False
    last_error: str | None = None
    schema_version: int = 1

@dataclass
class PolicyActivityOutput:
    """ Resultado da activity fetch_monitored_policy."""
    interval_seconds: int = 3600
    next_check_at: str | None = None
    paused: bool = False
    stability_score: int = 0
    scheduling_reason: str = "unknown"
    schema_version: int = 1

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyActivityOutput":
        """Desserializa a partir de dict ignorando campos desconhecidos."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

@dataclass
class WorkflowStateSnapshot:
    """ Snapshot genérico de estado do workflow persistido no Redis.

    Versão neutra de WorkflowSnapshot sem dependência de enums do orquestrador.
    Usada para observabilidade e health checks.
    """
    state: str = "active"
    monitored_id: str = ""
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_error: str | None = None
    attempt_count: int = 0
    schema_version: int = 1

class CollectionResult(BaseModel):
    """ Resultado de uma coleta reportada pelo sistema."""
    success: bool
    monitored_id: UUID
    trace_id: str = ""
    error: str | None = None
    collected_at: str | None = None


# ─────────────────────── Contratos de Orquestração (neutros) ──────────────────
# Migrados de market_orchestrator.schemas.* para eliminar inversão de dependência.
# market_orchestrator re-exporta daqui para backward compat interno.

@dataclass
class CollectionPolicy:
    """ Política de coleta para o workflow de monitoramento."""
    interval_seconds: int = 3600
    backoff_max_attempts: int = 5
    backoff_base_seconds: int = 60
    stability_score: int = 0
    scheduling_reason: str = ""

@dataclass
class WorkflowInput:
    """ Payload de entrada para início do workflow e Continue-As-New."""
    monitored_id: str
    user_id: str
    policy: CollectionPolicy = field(default_factory=CollectionPolicy)
    bootstrap_flags: dict = field(default_factory=dict)

@dataclass
class ResumeSignalPayload:
    """ Payload do signal de retomada."""
    immediate_collect: bool = False

@dataclass
class UpdatePolicySignalPayload:
    """ Payload do signal de atualização de política."""
    policy: CollectionPolicy = field(default_factory=CollectionPolicy)

@dataclass
class CompetitorChangedPayload:
    """ Payload do signal de mudança de concorrente."""
    event: Literal["added", "removed"] = "added"
    competitor_id: str = ""


__all__ = [
    "CollectionPayload",
    "validate_payload",
    "DispatchActivityOutput",
    "QueryStatusOutput",
    "PolicyActivityOutput",
    "WorkflowStateSnapshot",
    "CollectionResult",
    "CollectionPolicy",
    "WorkflowInput",
    "ResumeSignalPayload",
    "UpdatePolicySignalPayload",
    "CompetitorChangedPayload",
]
