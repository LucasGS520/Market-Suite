""" Define as rotas responsáveis por acionar o pipeline de scraping 

O módulo concentra o endpoint ``/scraper/parse`` responsável por 
executar o pipeline sequencial de scraping.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Body, Request, Response, status
import structlog

from shared.utils.logging_utils import sanitize_log_data
from shared.utils.url_validation import (
    UrlIssue,
    check_url_compatibility as shared_check_url_compatibility,
    normalize_product_url as shared_normalize_product_url,
)
from shared.schemas.schemas_scraper import ErrorResponse, ParserRequest, ParserResponse

from market_scraper.routes.response_helpers import (
    _http_error,
    _map_http_download_issue,
    _sanitize_payload,
    build_no_result_response,
    build_success_response,
)

from market_scraper.services.pipeline_factory import run_pipeline
from market_scraper.services.synergic_pipeline import PipelineTimeoutError
from market_scraper.utils.conditional_payload import (
    build_cache_headers,
    get_cached_response,
    invalidate_cached_response,
    parse_if_modified_since,
    should_return_not_modified,
    store_response,
)
from market_scraper.utils.http_utils import HostResolutionError, resolve_public_address
from market_scraper.utils.price import parse_price_str


logger = structlog.get_logger("routes_scraper")

def _ensure_public_endpoint(host: str) -> UrlIssue | None:
    """ Garante que apenas hosts públicos sejam processados pelo pipeline """
    #A resolução DNS utiliza utilitário compartilhado que bloqueia IPs privados e documenta eventuais falhas para facilitar auditoria de SSRF.
    try:
        resolve_public_address(host)
    except HostResolutionError as exc:
        return UrlIssue(code="blocked_host", message=str(exc))
    return None

router = APIRouter(tags=["scraper"])

@router.post(
    "/parse",
    response_model=ParserResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)

async def parse_endpoint(
    request: Request,
    response: Response,
    payload: ParserRequest = Body(...),
) -> ParserResponse | Response:
    """ Executa o pipeline sequencial, cuidando de respostas condicionais """
    trace_id = str(uuid4())
    request_logger = logger.bind(trace_id=trace_id)

    raw_url = str(payload.url)
    try:
        normalized_url = shared_normalize_product_url(raw_url)
    except ValueError as exc:
        issue = UrlIssue(code="invalid_url", message=str(exc))
        return _http_error(
            issue,
            status_code=status.HTTP_400_BAD_REQUEST,
            trace_id=trace_id,
            request_logger=request_logger,
            log_extra=_sanitize_payload(raw_url),
        )
    
    request_logger = request_logger.bind(url=sanitize_log_data(normalized_url))

    compatibility = shared_check_url_compatibility(
        normalized_url,
        ensure_public_endpoint=_ensure_public_endpoint,    
    )
    if compatibility:
        return _http_error(
            compatibility,
            status_code=status.HTTP_400_BAD_REQUEST,
            trace_id=trace_id,
            request_logger=request_logger,
        )
    
    force_refresh = bool(payload.metadata.get("force_refresh")) if payload.metadata else False
    cached_metadata = None
    if not force_refresh:
        cached_metadata = get_cached_response(normalized_url)
        if cached_metadata and should_return_not_modified(
            if_none_match=request.headers.get("if-none-match"),
            if_modified_since=parse_if_modified_since(request.headers.get("if-modified-since")),
            metadata=cached_metadata,
        ):
            headers = build_cache_headers(cached_metadata)
            request_logger.info(
                "parse_not_modified",
                url=sanitize_log_data(normalized_url),
                etag=cached_metadata.etag,
                source=cached_metadata.payload.source,
            )
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    try:
        outcome = await run_pipeline(normalized_url)
    except PipelineTimeoutError as exc:
        issue = UrlIssue(code="pipeline_timeout", message="Tempo limite do pipeline excedido")
        return _http_error(
            issue,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            trace_id=trace_id,
            request_logger=request_logger,
            log_extra={"error": sanitize_log_data(str(exc))},
        )
    
    http_issue = _map_http_download_issue(outcome)
    if http_issue:
        issue, status_code = http_issue
        invalidate_cached_response(normalized_url)
        return _http_error(
            issue,
            status_code=status_code,
            trace_id=trace_id,
            request_logger=request_logger,
        )

    if outcome.status != "success" or not outcome.payload:
        return build_no_result_response(
            outcome=outcome,
            request_logger=request_logger,
            trace_id=trace_id,
        )
    
    payload_data = outcome.payload

    try:
        price: Decimal = parse_price_str(
            payload_data.get("current_price"),
            normalized_url,
        )
    except ValueError as exc:
        issue = UrlIssue(code="invalid_price", message=str(exc))
        invalidate_cached_response(normalized_url)
        return _http_error(
            issue,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            trace_id=trace_id,
            request_logger=request_logger,
        )
    
    parse_response = build_success_response(
        payload_data,
        normalized_url=normalized_url,
        outcome=outcome,
        request_logger=request_logger,
        current_price=price,
    )
    metadata = store_response(normalized_url, parse_response)
    for key, value in build_cache_headers(metadata).items():
        response.headers[key] = value
    return parse_response


__all__ = ["router"]
