""" Contrato explícito de payload para coletas de produtos.

Define o schema canônico que circula entre o orquestrador, a fila Celery e a
task de coleta. Qualquer código que produza ou consuma payloads de coleta deve
usar ``CollectionPayload`` para garantir tipagem, validação e rastreamento.

Versionamento:
    version=1 — campo adicionado para compatibilidade futura. Payloads antigos
    sem o campo recebem version=1 automaticamente durante validação.

Fluxo esperado:
    Builder → CollectionPayload → .model_dump() → Celery queue (dict)
    Task recebe dict → validate_payload() → CollectionPayload → lógica da task
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


logger = logging.getLogger(__name__)


class CollectionPayload(BaseModel):
    """ Payload tipado para coletas de monitorados e concorrentes.

    Campos obrigatórios:
        kind: tipo da coleta — 'monitored' ou 'competitor'.
        monitored_id: UUID do produto monitorado raiz.
        url: URL a ser coletada pelo scraper.
        trace_id: identificador de rastreamento distribuído (gerado automaticamente se ausente).

    Campos opcionais:
        version: versão do schema para compatibilidade futura (padrão: 1).
        competitor_id: UUID do concorrente quando kind='competitor'.
        user_id: UUID do usuário dono do monitorado.
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

    competitor_id: UUID | None = Field(default=None, description="UUID do concorrente (apenas para kind=competitor)")
    user_id: UUID | None = Field(default=None, description="UUID do usuário dono do monitorado")
    enqueued_at: str | None = Field(default=None, description="ISO timestamp de enfileiramento")
    force_compare: str | None = Field(default=None, description="Flag para forçar comparação ('true'/'1')")
    collected_at: str | None = Field(default=None, description="ISO timestamp da coleta")
    name: str | None = Field(default=None, description="Nome para logs e depuração")

    @model_validator(mode="before")
    @classmethod
    def _ensure_trace_id(cls, data: dict) -> dict:
        """ Garante trace_id sempre preenchido — gera UUID se ausente ou vazio """
        if isinstance(data, dict) and not data.get("trace_id"):
            data["trace_id"] = str(uuid4())
        return data


def validate_payload(payload: dict | None) -> CollectionPayload:
    """ Valida dicionário de payload retornando CollectionPayload tipado.

    Aceita payloads antigos sem ``version`` e atribui ``version=1`` como fallback.
    Lança ``ValueError`` com mensagem descritiva se o payload for estruturalmente
    inválido (ex.: faltando ``kind``, ``monitored_id`` ou ``url``).

    Args:
        payload: dicionário bruto recebido do Celery ou de builders antigos.

    Returns:
        CollectionPayload validado e tipado.

    Raises:
        ValueError: se o payload for None ou contiver campos inválidos/ausentes.

    Exemplo::

        payload_dict = {"kind": "monitored", "monitored_id": "...", "url": "..."}
        typed = validate_payload(payload_dict)
        print(typed.trace_id)  # UUID gerado automaticamente
    """
    if payload is None:
        raise ValueError("Payload de coleta não pode ser None")

    try:
        return CollectionPayload.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"Payload de coleta inválido: {exc}") from exc


__all__ = [
    "CollectionPayload",
    "validate_payload",
]
