""" Modelos compartilhados do contrato HTTP entre ``market_alert`` e ``market_scraper``

Este módulo evita divergências de tipagem ao centralizar os esquemas de
requisição e resposta utilizados pelos serviços. A API pública envia
instâncias de :class:`ParserRequest` e valida o retorno por meio de
``ParserResponse``. O objetivo é manter um contrato único e versionado em
``shared`` para reduzir integrações frágeis ou condicionais dispersas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, Literal, Mapping, Optional
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
    currency: Optional[str] = Field(
        None,
        description="Moeda informada pelo scraper quando identificada",
    )
    availability: bool | None = Field(
        None,
        description="Disponibilidade reportada pelo scraper; ``False`` sinaliza anúncio inativo",
    )
    last_status: str | None = Field(
        None,
        description="Indicador textual do último estado conhecido do anúncio",
    )
    etag: str | None = Field(
        None, description="ETag devolvido pelo scraper para reutilizar condicionais"
    )
    not_modified: bool = Field(
        False, description="Indica uso de heurística de 304 mesmo com corpo presente"
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
    def _normalize_zero_price(cls, data: Any) -> Any:
        """ Converte preço zero em ``None`` para evitar histórico inválido """
        if not isinstance(data, Mapping):
            return data

        if "current_price" in data and data["current_price"] in {0, 0.0, "0", "0.0"}:
            rewritten = dict(data)
            rewritten["current_price"] = None
            rewritten.setdefault("last_status", "price_zero_filtered")
            return rewritten
        return data

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
    trace_id: str | None = Field(
        None,
        description="Identificador correlacionado com os logs estruturados",
    )

ScrapeResultStatus = Literal["success", "not_modified", "no_result", "error"]

@dataclass(slots=True)
class ScrapeResult:
    """ Resultado canônico utlizado pelas rotinas do ``market_alert``

    As tasks de coleta e rechecagem usam este contrato para evitar
    divergências entre monitorados e concorrentes. O campo ``status``
    segue os valores padronizados consumidos pelo collector:

    - ``success``: scraping realizado com dados válidos, podendo indicar
      mudança de preço ou disponibilidade.
    - ``not_modified``: o scraper retornou 304/ETag sem alterações.
    - ``no_result``: não houve dados confiáveis (ex.: anúncio inexistente).
    - ``error``: falha controlada mapeada pelo cliente ou serviço chamador.
    """
    status: ScrapeResultStatus
    product_id: str | None = None
    price_changed: bool = False
    availability_changed: bool = False
    http_status: int | None = None
    error_code: str | None = None
    retry_after: int | None = None
    persisted_at: datetime | None = None

    def __getitem__(self, item: str):
        """ Permite acesso estilo dicionário para compatibilidade retroativa """
        return getattr(self, item)


__all__ = [
    "ParserRequest",
    "ParserResponse",
    "ErrorResponse",
]
