""" Testes para o cache condicional de respostas do scraper """

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal

from backend.shared.schemas.shared_schemas_scraper import ParserResponse

from market_scraper.utils import cache
from market_scraper.utils.conditional_payload import (
    build_cache_headers,
    get_cached_response,
    parse_if_modified_since,
    should_return_not_modified,
    store_response,
)


def _build_payload() -> ParserResponse:
    """ Cria payload padrão reutilizado pelos cenários de teste """
    return ParserResponse(
        name="Produto Teste",
        current_price=Decimal("10.50"),
        url="https://example.com/produto",
        source="example.com",
    )

def test_store_response_and_get_cached_metadata() -> None:
    """ Garante round-trip completo ao armazenar e recuperar payload """
    cache.clear()
    payload = _build_payload()
    metadata = store_response(str(payload.url), payload)

    cached = get_cached_response(str(payload.url))
    assert cached is not None
    assert cached.etag == metadata.etag
    assert cached.payload.current_price == payload.current_price

    headers = build_cache_headers(metadata)
    assert headers["ETag"] == metadata.quoted_etag
    assert headers["Cache-Control"] == "max-age=0, must-revalidate"

def test_should_return_not_modified_by_if_none_match() -> None:
    """Valida que ``If-None-Match`` correspondente devolve 304"""

    cache.clear()
    payload = _build_payload()
    metadata = store_response(str(payload.url), payload)

    assert should_return_not_modified(
        if_none_match=metadata.quoted_etag,
        if_modified_since=None,
        metadata=metadata,
    )


def test_should_return_not_modified_by_if_modified_since() -> None:
    """Confirma 304 quando a data enviada é posterior ao ``Last-Modified``"""

    cache.clear()
    payload = _build_payload()
    metadata = store_response(str(payload.url), payload)

    future = metadata.last_modified + timedelta(seconds=5)
    header_value = future.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    parsed_header = parse_if_modified_since(header_value)

    assert parsed_header is not None
    assert should_return_not_modified(
        if_none_match=None,
        if_modified_since=parsed_header,
        metadata=metadata,
    )


def test_parse_if_modified_since_handles_invalid_header() -> None:
    """Garante ``None`` quando o cabeçalho não segue formato válido"""

    assert parse_if_modified_since("not a date") is None
    