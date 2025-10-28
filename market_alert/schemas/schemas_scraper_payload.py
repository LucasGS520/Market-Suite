""" Esquemas usados para validar respostas do serviço de scraping """

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ScraperPayload(BaseModel):
    """ Representa payload mínimo aceito pelo ``market_scraper`` """
    name: str = Field(..., description="Nome identificado do produto")
    current_price: Decimal = Field(..., description="Preço atual normalizado")
    url: HttpUrl = Field(..., description="URL processada pelo scraper")
    source: str = Field(..., description="Origem atribuída pelo scraper")
    currency: Optional[str] = Field(None, description="Código de moeda ISO-4217")
    etag: Optional[str] = Field(None, description="ETag devolvido pelo scraper")
    last_modified: Optional[datetime] = Field(None, description="Timestamp HTTP Last-Modified")
    payload: Optional[dict[str, Any]] = Field(None, description="Payload bruto opcional")
    timestamp: Optional[datetime] = Field(None, description="Momento de coleta no scraper")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """ Garante nome preenchido após remoção de espaços """
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
        """ Normaliza moeda para letras maiúsculas e max 8 caracteres """
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned[:8] if cleaned else None
    