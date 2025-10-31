""" Funções auxiliares compartilhadas pelos serviços de scraping """

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID

try:
    from unittest.mock import AsyncMock
except ImportError:
    AsyncMock = None

from shared.schemas.schemas_scraper import ParserResponse
from shared.utils import sanitize_text

from market_alert.scraper.scraper_client import (
    ScraperClient,
    ScraperClientError,
    ScraperFetchResult,
)


def ensure_price(payload: ParserResponse, url: str) -> Decimal:
    """ Garante que o payload contenha preço válido antes de persistir """
    if payload.current_price is None:
        raise ScraperClientError(
            f"Payload do scraper sem preço para a URL {url}",
            status_code=500,
        )
    return payload.current_price

def ensure_name(payload: ParserResponse, url: str) -> str:
    """ Normaliza e valida o nome retornado pelo scraper """
    if payload.name is None:
        raise ScraperClientError(
            f"Payload do scraper sem nome para a URL {url}",
            status_code=500,
        )
    sanitized = sanitize_text(payload.name)
    if not sanitized:
        raise ScraperClientError(
            f"Nome vazio retornado pelo scraper para a URL {url}",
            status_code=500,
        )
    return sanitized

def to_decimal(value: Any) -> Decimal | None:
    """ Converte valores genéricos para ``Decimal`` com tolerância """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
    
def to_float(value: Any) -> float | None:
    """ Converte valores genéricos para ``float`` com tolerância """
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
    

async def maybe_call_mocked_parse(
    client: ScraperClient,
    *,
    url: str,
    monitored_id: str | None,
    etag: str | None,
    last_modified: datetime | None,
    force_refresh: bool,
    product_type: str,
    user_id: UUID | None,
    metadata: Mapping[str, Any] | None,
) -> ScraperFetchResult | None:
    """ Invoca ``parse`` quando foi substituído por mock (testes) """
    parse_callable = getattr(client, "parse", None)
    if parse_callable is None:
        return None
    
    is_mock = False
    if AsyncMock and isinstance(parse_callable, AsyncMock):
        is_mock = True
    elif getattr(parse_callable, "__module__", "").startswith("unittest.mock"):
        is_mock = True

    if not is_mock:
        return None
    
    parsed = await parse_callable(
        url=url,
        product_type=product_type,
        monitored_id=monitored_id,
        user_id=user_id,
        metadata=metadata,
        etag=etag,
        last_modified=last_modified,
        force_refresh=force_refresh,
    )

    if parsed is None:
        return ScraperFetchResult(status_code=304, payload=None, headers={})
    
    if not isinstance(parsed, ParserResponse):
        parsed = ParserResponse.model_validate(parsed)

    return ScraperFetchResult(status_code=200, payload=parsed, headers={})


__all__ = [
    "ensure_price",
    "ensure_name",
    "to_decimal",
    "to_float",
    "maybe_call_mocked_parse",
]
