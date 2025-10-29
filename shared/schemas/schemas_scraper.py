""" Modelos Pydantic compartilhados entre ``market_alert`` e ``market_scraper``

O objetivo deste módulo é garantir que ambos os serviços conversem através
do mesmo contrato de scraping, evitando divergências de campos ou tipos.
As classes expostas aqui são utilizadas diretamente pelas rotas HTTP do
``market_scraper`` e pelos consumidores no ``market_alert``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator


class _BaseUrlPayload(BaseModel):
    """ Normaliza campos que dependem de URL para os contratos compartilhados """
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
    """ Contrato mínimo aceito pelas rotas ``/scraper/parse`` ou ``/scrape/parse`` """
    product_type: Literal["monitored", "competitor"] | None = Field(
        None,
        description="Contexto opcional indicando se a URL pertence a monitorados ou concorrentes",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Campos adicionais livres para auditoria ou depuração",
    )

class ScraperRequest(_BaseUrlPayload):
    """ Contrato legado utilizado por chamadas internas do ``market_alert`` """
    product_type: Literal["monitored", "competitor"] = Field(
        "monitored",
        description="Tipo padrão utilizado quando o cliente não especifica explicitamente",
    )
    user_id: UUID | None = Field(
        None,
        description="Identificador do usuário ligado ao monitoramento (quando disponível)",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Campos adicionais livres para auditoria ou depuração",
    )

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

class ScraperResponse(ParserResponse):
    """ Contrato expandido utilizado pelos modelos internos do ``market_alert`` """
    old_price: Decimal | None = Field(
        None,
        description="Preço anterior conhecido, útil para detectar oscilações",
    )
    thumbnail: str | None = Field(None, description="Miniatura ilustrativa do produto")
    free_shipping: bool = Field(False, description="Indica frete grátis quando identificado")
    seller: str | None = Field(
        None,
        description="Nome ou identificador do vendedor reportado pelo marketplace",
    )
    shipping: str | None = Field(
        None,
        description="Detalhes textuais de envio extraídos durante o parsing",
    )


__all__ = [
    "ParserRequest",
    "ParserResponse",
    "ScraperRequest",
    "ScraperResponse",
]
