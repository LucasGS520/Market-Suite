""" Modelos compartilhados do contrato HTTP entre ``market_alert`` e ``market_scraper``.

Este modulo centraliza os esquemas de request/response usados pelos servicos
para manter um contrato unico, versionado e resiliente a evolucoes aditivas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, Literal, Mapping, Optional, get_args
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from pydantic import field_validator, model_validator


SCRAPER_CONTRACT_VERSION = "v1"
SCRAPER_CONTRACT_VERSION_HEADER = "X-MarketScraper-Contract-Version"
SCRAPER_CONTRACT_IMPLEMENTATION = "shared.schemas.shared_schemas_scraper"
SCRAPER_CONTRACT_CHANGELOG_PATH = "backend/shared/CONTRATO_HTTP_SCRAPER.md"
SCRAPER_CONTRACT_COMPATIBILITY_POLICY = (
    "Mudancas aditivas nao breaking sao permitidas dentro de v1 quando "
    "introduzem apenas campos opcionais ou detalhes suplementares "
    "ignoraveis. Mudancas breaking exigem nova versao major do contrato."
)

SCRAPER_REQUEST_REQUIRED_FIELDS = ("url",)
SCRAPER_REQUEST_OPTIONAL_FIELDS = ("product_type", "user_id", "metadata")
SCRAPER_RESPONSE_REQUIRED_FIELDS: tuple[str, ...] = ()
SCRAPER_RESPONSE_OPTIONAL_FIELDS = (
    "name",
    "current_price",
    "currency",
    "availability",
    "last_status",
    "etag",
    "not_modified",
    "url",
    "source",
    "payload",
    "no_result",
)
SCRAPER_ERROR_RESPONSE_REQUIRED_FIELDS = ("message", "error_code")
SCRAPER_ERROR_RESPONSE_OPTIONAL_FIELDS = ("trace_id",)

SCRAPER_HTTP_SUCCESS_CODES = (200, 304)
SCRAPER_HTTP_ERROR_CODES = (400, 403, 422, 429, 504)
SCRAPER_HTTP_CODES = SCRAPER_HTTP_SUCCESS_CODES + SCRAPER_HTTP_ERROR_CODES

ScraperErrorCode = Literal[
    "invalid_url",
    "blocked_host",
    "unsupported_by_robots",
    "too_many_redirects",
    "anti_bot_page",
    "no_result",
    "pipeline_timeout",
]
SCRAPER_ALLOWED_ERROR_CODES = get_args(ScraperErrorCode)


class _BaseUrlPayload(BaseModel):
    """ Normaliza campos baseados em URL compartilhados pelos contratos. """

    model_config = ConfigDict(extra="ignore")
    url: AnyHttpUrl = Field(..., description="Endereco do produto a ser processado")
    _http_prefixes: ClassVar[tuple[str, str]] = ("http://", "https://")

    @field_validator("url", mode="before")
    @classmethod
    def _ensure_scheme(cls, value: str) -> str:
        """ Garante que URLs parciais recebam ``https://`` antes da validacao. """
        if isinstance(value, str) and not value.startswith(cls._http_prefixes):
            return f"https://{value}"
        return value

class ParserRequest(_BaseUrlPayload):
    """ Contrato aceito pela rota ``/scraper/parse``. """

    product_type: Literal["monitored", "competitor"] = Field(
        "monitored",
        description="Contexto indicando se a URL pertence a monitorados ou concorrentes",
    )
    user_id: UUID | None = Field(
        None,
        description="Identificador do usuario relacionado a requisicao quando aplicavel",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Campos adicionais livres utilizados para rastreio e auditoria",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_metadata(cls, data: Any) -> Any:
        """ Remove metadados vazios para preservar compatibilidade. """
        if isinstance(data, dict):
            metadata = data.get("metadata")
            if metadata in ({}, []):
                rewritten = dict(data)
                rewritten.pop("metadata", None)
                return rewritten
        return data

class ParserResponse(BaseModel):
    """ Resposta padronizada contendo os atributos essenciais do scraping. """

    name: str | None = Field(None, description="Nome normalizado do produto")
    current_price: Decimal | None = Field(
        None,
        description="Preco atual capturado pelo scraper em formato decimal",
    )
    currency: Optional[str] = Field(
        None,
        description="Moeda informada pelo scraper quando identificada",
    )
    availability: bool | None = Field(
        None,
        description="Disponibilidade reportada pelo scraper; False sinaliza anuncio inativo",
    )
    last_status: str | None = Field(
        None,
        description="Indicador textual do ultimo estado conhecido do anuncio",
    )
    etag: str | None = Field(
        None,
        description="ETag devolvido pelo scraper para reutilizar condicionais",
    )
    not_modified: bool = Field(
        False,
        description="Indica uso de heuristica de 304 mesmo com corpo presente",
    )
    url: AnyHttpUrl | None = Field(
        None,
        description="URL canonica utilizada na coleta",
    )
    source: str | None = Field(
        None,
        description="Identificador do marketplace ou host de onde os dados foram extraidos",
    )
    payload: dict[str, Any] | None = Field(
        None,
        description="Dados suplementares mantidos para rastreabilidade do parsing",
    )
    no_result: bool = Field(
        False,
        description="Indica se o scraper concluiu sem resultado confiavel",
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        """ Remove espacos extras de nomes informados pelo scraper. """
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="before")
    @classmethod
    def _normalize_zero_price(cls, data: Any) -> Any:
        """ Converte preco zero em ``None`` para evitar historico invalido. """
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
        """ Permite aceitar ``marketplace`` como alias de ``source``. """
        if isinstance(data, dict) and "marketplace" in data:
            transformed = dict(data)
            transformed.setdefault("source", transformed.pop("marketplace"))
            return transformed
        return data

class ErrorResponse(BaseModel):
    """ Estrutura de erro retornada pela rota ``/scraper/parse``. """

    message: str = Field(..., description="Descricao humanizada de erro")
    error_code: ScraperErrorCode = Field(
        ...,
        description="Codigo categorico permitido pelo contrato HTTP do scraper",
    )
    trace_id: str | None = Field(
        None,
        description="Identificador correlacionado com os logs estruturados",
    )


ScrapeResultStatus = Literal["success", "not_modified", "no_result", "error"]

@dataclass(slots=True)
class ScrapeResult:
    """ Resultado canonico utilizado pelas rotinas do ``market_alert``. """

    status: ScrapeResultStatus
    product_id: str | None = None
    price_changed: bool = False
    availability_changed: bool = False
    http_status: int | None = None
    error_code: str | None = None
    retry_after: int | None = None
    persisted_at: datetime | None = None

    def __getitem__(self, item: str):
        """ Permite acesso estilo dicionario para compatibilidade retroativa. """
        return getattr(self, item)


__all__ = [
    "SCRAPER_ALLOWED_ERROR_CODES",
    "SCRAPER_CONTRACT_CHANGELOG_PATH",
    "SCRAPER_CONTRACT_COMPATIBILITY_POLICY",
    "SCRAPER_CONTRACT_IMPLEMENTATION",
    "SCRAPER_CONTRACT_VERSION",
    "SCRAPER_CONTRACT_VERSION_HEADER",
    "SCRAPER_ERROR_RESPONSE_OPTIONAL_FIELDS",
    "SCRAPER_ERROR_RESPONSE_REQUIRED_FIELDS",
    "SCRAPER_HTTP_CODES",
    "SCRAPER_HTTP_ERROR_CODES",
    "SCRAPER_HTTP_SUCCESS_CODES",
    "SCRAPER_REQUEST_OPTIONAL_FIELDS",
    "SCRAPER_REQUEST_REQUIRED_FIELDS",
    "SCRAPER_RESPONSE_OPTIONAL_FIELDS",
    "SCRAPER_RESPONSE_REQUIRED_FIELDS",
    "ErrorResponse",
    "ParserRequest",
    "ParserResponse",
    "ScrapeResult",
    "ScrapeResultStatus",
]
