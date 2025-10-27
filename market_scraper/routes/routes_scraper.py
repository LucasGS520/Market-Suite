""" Define as rotas responsáveis por acionar o pipeline de scraping 

O módulo concentra o endpoint ``/parse`` responsável por executar o
pipeline sequencial de scraping.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Body, status
import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.routes.response_helpers import (
    _http_error,
    _map_http_download_issue,
    _sanitize_payload,
    build_no_result_response,
    build_success_response,
)
from market_scraper.schemas.parse import ErrorResponse, ParseRequest, ParserResponse
from market_scraper.services.services_scraper_common import run_pipeline
from market_scraper.services.synergic_pipeline import PipelineTimeoutError
from market_scraper.utils.price import parse_price_str
from market_scraper.utils.url_validation import UrlIssue, check_url_compatibility, normalize_product_url


logger = structlog.get_logger("routes_scraper")

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
async def parse_endpoint(payload: ParseRequest = Body(...)) -> ParserResponse:
    """ Executa o pipeline sequencial e retorna payload padronizado """
    trace_id = str(uuid4())
    request_logger = logger.bind(trace_id=trace_id)

    try:
        normalized_url = normalize_product_url(payload.url)
    except ValueError as exc:
        issue = UrlIssue(code="invalid_url", message=str(exc))
        return _http_error(
            issue,
            status_code=status.HTTP_400_BAD_REQUEST,
            trace_id=trace_id,
            request_logger=request_logger,
            log_extra=_sanitize_payload(payload.url),
        )
    
    request_logger = request_logger.bind(url=sanitize_log_data(normalized_url))

    compatibility = check_url_compatibility(normalized_url)
    if compatibility:
        return _http_error(
            compatibility,
            status_code=status.HTTP_400_BAD_REQUEST,
            trace_id=trace_id,
            request_logger=request_logger,
        )
    
    try:
        outcome = await run_pipeline(normalized_url)
    except PipelineTimeoutError as exc:
        issue = UrlIssue(code="pipeline_timeout", message="Tempo limite do pipeline execedido")
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
        price = parse_price_str(payload_data.get("current_price"), normalized_url)
    except ValueError as exc:
        issue = UrlIssue(code="invalid_price", message=str(exc))
        return _http_error(
            issue,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            trace_id=trace_id,
            request_logger=request_logger,
        )
    
    response = build_success_response(
        payload_data,
        normalized_url=normalized_url,
        outcome=outcome,
        request_logger=request_logger,
        current_price=price,
    )
    return response


__all__ = ["router"]
