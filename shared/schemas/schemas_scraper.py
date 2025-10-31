""" Modelos compartilhados do contrato HTTP entre ``market_alert`` e ``market_scraper``

Este módulo evita divergências de tipagem ao centralizar os esquemas de
requisição e resposta utilizados pelos serviços. A API pública envia
instâncias de :class:`ParserRequest` e valida o retorno por meio de
``ParserResponse``. O objetivo é manter um contrato único e versionado em
``shared`` para reduzir integrações frágeis ou condicionais dispersas.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from pydantic import field_validator, model_validator


class _BaseUrlPayload(BaseModel):
    """ Normaliza campos baseados em URL compartilhados pelos contratos """
    model_config = ConfigDict(extra="ignore")
    url: AnyHttpUrl = Field(..., description="Endereço do produto a ser processado")
    _http_prefixes: ClassVar[tuple[str, str]] = ("http://", "https://")

    @field_validator("url", mode="before")
    @classmethod
    def _ensure_scheme(cls, value: str) -> str:
        """ Garante que URLs parciais recebam ``https://`` antes da validação """
        #Mantemos a lógica aqui para ser reaproveitada por todas as requisições baseadas em URL
        if isinstance(value, str) and not value.startswith(cls._http_prefixes):
            return f"https://{value}"
        return value

class ParserRequest(_BaseUrlPayload):
    """ Contrato aceito pela rota ``/scraper/parse`` """
    product_type: Literal["monitored", "competitor"] = Field(
        "monitored",
        description="Contexto indicando se a URL pertence a monitorados ou concorrentes",
    )
    user_id: UUID | None = Field(
        None,
        description="Identificador do usuário relacionado à requisição (quando aplicável)",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Campos adicionais livres utilizados para rastreio e auditoria",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_metadata(cls, data: Any) -> Any:
        """ Remove metadados vazios para preservar compatibilidade """
        if isinstance(data, dict):
            metadata = data.get("metadata")
            if metadata in ({}, []):
                rewritten = dict(data)
                rewritten.pop("metadata", None)
                return rewritten
        return data

class ParserResponse(BaseModel):
    """ Resposta padronizada contendo os atributos essenciais do scraping """
    name: str | None = Field(None, description="Nome normalizado do produto")
    current_price: Decimal | None = Field(
        None,
        description="Preço atual capturado pelo scraper em formato decimal",
    )
    url: AnyHttpUrl | None = Field(
        None,
        description="URL canônica utilizada na coleta",
    )
    source: str | None = Field(
        None,
        description="Identificador do marketplace ou host de onde os dados foram extraídos",
    )
    payload: dict[str, Any] | None = Field(
        None,
        description="Dados suplementares mantidos para rastreabilidade do parsing",
    )
    no_result: bool = Field(
        False,
        description="Indica se o scraper concluiu sem resultado confiável",
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        """ Remove espaços extras de nomes informados pelo scraper """

        #A higienização mantém consistência ao comparar valores entre serviços.
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="before")
    @classmethod
    def _apply_marketplace_alias(cls, data: Any) -> Any:
        """ Permite aceitar ``marketplace`` como alias de ``source`` sem duplicar campos """
        if isinstance(data, dict) and "marketplace" in data:
            #Ao receber payloads antigos ainda usando ``marketplace``, convertemos para ``source``
            transformed = dict(data)
            transformed.setdefault("source", transformed.pop("marketplace"))
            return transformed
        return data

class ErrorResponse(BaseModel):
    """ Estrutura de erros retornados pela rota ``/scraper/parse`` """
    message: str = Field(..., description="Descrição humanizada de erro")
    error_code: str = Field(..., description="Código categórico que identifica o erro encontrado")
    trace_id: str | None = Field(..., description="Identificador correlacionado com os logs estruturados")

@dataclass(slots=True)
class ScrapeResult:
    """ Resultado canônico utlizado pelas rotinas do ``market_alert`` """
    status: str
    product_id: str | None = None
    price_changed: bool = False
    http_status: int | None = None
    error_code: str | None = None
    retry_after: int | None = None

    def __getitem__(self, item: str):
        """ Permite acesso estilo dicionário para compatibilidade retroativa """
        return getattr(self, item)


__all__ = [
    "ParserRequest",
    "ParserResponse",
    "ErrorResponse",
]
