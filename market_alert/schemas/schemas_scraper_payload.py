""" Esquemas usados para validar respostas do serviço de scraping """

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, HttpUrl, field_validator

from shared.schemas.schemas_scraper import ParserResponse


class ScraperPayload(ParserResponse):
    """ Especializa o contrato compartilhado com campos usados internamente """
    url: HttpUrl = Field(..., description="URL processada pelo scraper")
    current_price: Decimal | None = Field(None, description="Preço atual normalizado")
    currency: str | None = Field(None, description="Código de moeda ISO-4217")
    etag: str | None = Field(None, description="ETag devolvido pelo scraper")
    last_modified: datetime | None = Field(None, description="Timestamp HTTP Last-Modified")
    payload: dict[str, Any] | None = Field(None, description="Payload bruto opcional")
    timestamp: datetime | None = Field(None, description="Momento de coleta no scraper")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str:
        """ Garante nome preenchido após remoção de espaços """
        if value is None:
            msg = "campo name ausente no payload do scraper"
            raise ValueError(msg)
        if not value or not value.strip():
            raise ValueError("campo name vazio no payload do scraper")
        return value.strip()
    
    @field_validator("current_price", mode="before")
    @classmethod
    def _validate_price(cls, value: Any) -> Decimal:
        """ Normaliza e valida o preço recebido """
        try:
            price = Decimal(str(value))
        except Exception as exc:
            raise ValueError("preço inválido no payload do scraper") from exc
        if price <= 0:
            raise ValueError("preço deve ser maior que zero")
        return price
    
    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: str | None) -> str | None:
        """ Normaliza moeda para letras maiúsculas e até oito caracteres """
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned[:8] if cleaned else None
    