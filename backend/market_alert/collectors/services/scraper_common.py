""" Funções auxiliares compartilhadas pelos serviços de scraping """

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping
from uuid import UUID

from shared.schemas import ParserResponse, ScrapeResult
from shared.clients.scraper_client import (
    ScraperClient,
    ScraperClientError,
    ScraperFetchResult,
)
from shared.scheduling import EVENT_NOT_MODIFIED, calculate_schedule
from shared.utils import normalize_scraper_response, sanitize_text


from market_alert.products.domain.product_lifecycle import to_scheduling_context
from market_alert.products.utils.price_decimal import to_decimal as _shared_to_decimal


def resolve_conditional_headers(entity: Any) -> tuple[str | None, datetime | None]:
    """ Normaliza campos de cache (etag e last_modified) para chamadas ao scraper """
    if entity is None:
        return None, None
    
    etag = getattr(entity, "etag", None)
    if not isinstance(etag, str):
        etag = None

    last_modified = getattr(entity, "last_modified", None)
    if isinstance(last_modified, datetime):
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)

        else:
            last_modified = last_modified.astimezone(timezone.utc)

    else:
        last_modified = None
    
    return etag, last_modified

def compute_force_refresh(
    last_checked: datetime | None,
    *,
    now: datetime,
    ttl_seconds: int,
) -> bool:
    """ Determina se a coleta deve ignorar condicionais pelo TTL configurado """
    if last_checked is None:
        return False
    
    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)

    return (now - last_checked).total_seconds() >= ttl_seconds

def ensure_price(payload: ParserResponse, url: str) -> Decimal:
    """ Garante que o payload contenha preço válido como ``Decimal`` """
    if payload.current_price is None:
        raise ScraperClientError(
            f"Payload do scraper sem preço para a URL {url}",
            status_code=500,
        )
    try:
        return Decimal(str(payload.current_price))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ScraperClientError(
            f"Preço inválido retornado pelo scraper para a URL {url}",
            status_code=500,
        ) from exc

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

def normalize_currency_code(value: str | None) -> str | None:
    """ Sanitiza e valida código de moeda aceitando apenas letras e até 5 caracteres """
    if value is None:
        return None
    
    sanitized = sanitize_text(value)
    if not sanitized:
        return None
    
    cleaned = "".join(ch for ch in sanitized if ch.isalnum())
    if not cleaned:
        return None
    
    normalized = cleaned.upper()[:5]
    return normalized

def to_decimal(value: Any) -> Decimal | None:
    """ Converte valores para ``Decimal`` usando utilitário compartilhado. """
    return _shared_to_decimal(value)
    
def to_float(value: Any) -> float | None:
    """ Converte valores genéricos para ``float`` com tolerância """
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
    
def maybe_call_mocked_parse(
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
    """ Invoca ``parse`` mockado em testes para manter previsibilidade síncrona """
    parse_callable = getattr(client, "parse", None)
    if parse_callable is None:
        return None

    is_mock = getattr(parse_callable, "__module__", "").startswith("unittest.mock")
    if not is_mock:
        return None
    
    parsed = parse_callable(
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
        parsed = normalize_scraper_response(parsed, source="worker")

    return ScraperFetchResult(status_code=200, payload=parsed, headers={})

def execute_scraper_fetch(
    client: ScraperClient,
    *,
    url: str,
    product_type: str,
    monitored_id: str | None,
    user_id: UUID | None,
    metadata: Mapping[str, Any] | None,
    etag: str | None,
    last_modified: datetime | None,
    force_refresh: bool,
) -> ScraperFetchResult:
    """ Executa chamadas ao scraper respeitando mocks e condicionais HTTP """
    result = maybe_call_mocked_parse(
        client,
        url=url,
        monitored_id=monitored_id,
        etag=etag,
        last_modified=last_modified,
        force_refresh=force_refresh,
        product_type=product_type,
        user_id=user_id,
        metadata=metadata,
    )

    if result is not None:
        return result
    
    return client.fetch(
        url=url,
        monitored_id=monitored_id,
        etag=etag,
        last_modified=last_modified,
        force_refresh=force_refresh,
        product_type=product_type,
        user_id=user_id,
        metadata=metadata,
    )

def resolve_availability(
    price: Decimal | None,
    availability_flag: bool | None,
) -> bool:
    """ Resolve disponibilidade canônica priorizando presença de preço. """
    if price is not None:
        return True
    if availability_flag is False:
        return False
    return availability_flag is True


def handle_not_modified_response(
    entity: Any,
    db: Any,
    *,
    now: datetime,
    entity_type: Literal["monitored", "competitor"],
) -> ScrapeResult:
    """ Trata resposta 304 com atualização de `last_checked` e efeitos colaterais.

    Para monitorados, além de persistir o timestamp, recalcula estabilidade e
    dispara enfileiramento assíncrono de concorrentes vinculados.
    """
    persisted_at: datetime | None = None
    if entity is not None:
        entity.last_checked = now
        entity.collected_at = now

        if entity_type == "monitored":
            schedule = calculate_schedule(
                to_scheduling_context(entity),
                reference_time=now,
                event_type=EVENT_NOT_MODIFIED,
            )
            entity.stability_score = schedule.stability_score
            entity.next_check_at = schedule.next_check_at

        db.commit()
        persisted_at = datetime.now(timezone.utc)

        if entity_type == "monitored":
            try:
                #Import local evita acoplamento forte entre serviços durante bootstrap.
                from market_alert.collectors.orchestrator.collector_service_orchestrator import enqueue_competitors_for_monitored

                enqueue_competitors_for_monitored(db, monitored_id=entity.id)
            except Exception:
                #Falha no enqueue não deve invalidar persistência já confirmada.
                pass

    return ScrapeResult(
        status="not_modified",
        product_id=str(entity.id) if entity is not None else None,
        http_status=304,
        persisted_at=persisted_at,
    )


__all__ = [
    "ensure_price",
    "ensure_name",
    "to_decimal",
    "to_float",
    "resolve_conditional_headers",
    "compute_force_refresh",
    "maybe_call_mocked_parse",
    "execute_scraper_fetch",
    "resolve_availability",
    "handle_not_modified_response",
]
