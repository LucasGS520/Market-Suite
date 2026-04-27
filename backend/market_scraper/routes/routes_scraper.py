""" Define as rotas responsáveis por acionar o pipeline de scraping 

O módulo concentra o endpoint ``/scraper/parse`` responsável por 
executar o pipeline sequencial de scraping.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Request, Response, status
from fastapi.responses import JSONResponse
from structlog.stdlib import BoundLogger

from shared.utils.logging_utils import sanitize_log_data
from shared.utils.url_validation import (
    UrlIssue,
    check_url_compatibility as shared_check_url_compatibility,
    normalize_product_url as shared_normalize_product_url,
)
from shared.schemas.shared_schemas_scraper import (
    ErrorResponse,
    ParserRequest,
    ParserResponse,
    SCRAPER_CONTRACT_VERSION,
    SCRAPER_CONTRACT_VERSION_HEADER,
)

from market_scraper.scraper_orchestrator.parse_product import (
    ParseProductError,
    ParseProductNoResult,
    ParseProduct,
)
from market_scraper.infra.cache.conditional_payload import (
    build_cache_headers,
    get_cached_response,
    invalidate_cached_response,
    parse_if_modified_since,
    should_return_not_modified,
    store_response,
)
from market_scraper.infra.logging.structured_logger import get_scraper_logger
from market_scraper.utils.http_utils import HostResolutionError, resolve_public_address
from market_scraper.utils.response_builder import build_no_result_response


logger = get_scraper_logger("routes_scraper")

_CONTRACT_VERSION_HEADER_DOC = {
    SCRAPER_CONTRACT_VERSION_HEADER: {
        "description": "Versao major do contrato HTTP do scraper.",
        "schema": {"type": "string", "example": SCRAPER_CONTRACT_VERSION},
    }
}

_PARSE_ROUTE_RESPONSES = {
    200: {
        "model": ParserResponse,
        "description": "Parse concluido com payload normalizado.",
        "headers": _CONTRACT_VERSION_HEADER_DOC,
    },
    304: {
        "description": "Representacao nao modificada para ETag/Last-Modified.",
        "headers": _CONTRACT_VERSION_HEADER_DOC,
    },
    400: {
        "model": ErrorResponse,
        "description": "Requisicao invalida ou host bloqueado antes do pipeline.",
        "headers": _CONTRACT_VERSION_HEADER_DOC,
    },
    403: {
        "model": ErrorResponse,
        "description": "URL bloqueada por regras de robots.txt.",
        "headers": _CONTRACT_VERSION_HEADER_DOC,
    },
    422: {
        "model": ErrorResponse,
        "description": "No result ou falha semantica detectada durante o parse.",
        "headers": _CONTRACT_VERSION_HEADER_DOC,
    },
    429: {
        "model": ErrorResponse,
        "description": "Pagina anti-bot detectada ou limite de requisicoes atingido para o dominio.",
        "headers": _CONTRACT_VERSION_HEADER_DOC,
    },
    503: {
        "model": ErrorResponse,
        "description": "Servico degradado: fallback de browser indisponivel.",
        "headers": _CONTRACT_VERSION_HEADER_DOC,
    },
    504: {
        "model": ErrorResponse,
        "description": "Pipeline excedeu o tempo limite documentado.",
        "headers": _CONTRACT_VERSION_HEADER_DOC,
    },
}


def _extract_log_correlation_context(metadata: dict[str, Any] | None) -> dict[str, str | None]:
    """ Extrai campos canônicos de correlação para binding estruturado. """
    metadata = metadata or {}
    return {
        "trace_id": str(metadata.get("trace_id") or uuid4()),
        "correlation_id": (
            str(metadata.get("correlation_id")) if metadata.get("correlation_id") is not None else None
        ),
        "monitored_id": (
            str(metadata.get("monitored_id")) if metadata.get("monitored_id") is not None else None
        ),
        "competitor_id": (
            str(metadata.get("competitor_id")) if metadata.get("competitor_id") is not None else None
        ),
    }

def _ensure_public_endpoint(host: str) -> UrlIssue | None:
    """ Garante que apenas hosts públicos sejam processados pelo pipeline """
    #A resolução DNS utiliza utilitário compartilhado que bloqueia IPs privados e documenta eventuais falhas para facilitar auditoria de SSRF.
    try:
        resolve_public_address(host)
    except HostResolutionError as exc:
        return UrlIssue(code="blocked_host", message=str(exc))
    return None

def _sanitize_invalid_url_log_payload(url: str) -> dict[str, str]:
    """Normaliza URL inválida antes do registro em log."""
    return {"url": sanitize_log_data(url)}

def _build_error_response(
    issue: UrlIssue,
    *,
    status_code: int,
    trace_id: str,
    request_logger: BoundLogger,
    log_extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Monta resposta JSON padronizada para erros do endpoint."""
    request_logger.warning(
        "parse_error",
        error_code=issue.code,
        http_status=status_code,
        message=issue.message,
        **dict(log_extra or {}),
    )
    return JSONResponse(
        status_code=status_code,
        headers={SCRAPER_CONTRACT_VERSION_HEADER: SCRAPER_CONTRACT_VERSION},
        content={
            "message": issue.message,
            "error_code": issue.code,
            "trace_id": trace_id,
        },
    )

router = APIRouter(tags=["scraper"])

@router.post(
    "/parse",
    response_model=ParserResponse,
    responses=_PARSE_ROUTE_RESPONSES,
)

async def parse_endpoint(
    request: Request,
    response: Response,
    payload: ParserRequest = Body(...),
) -> ParserResponse | Response:
    """ Executa o pipeline sequencial, cuidando de respostas condicionais """
    log_context = _extract_log_correlation_context(payload.metadata)
    trace_id = log_context["trace_id"]
    request_logger = logger.bind(**log_context)

    raw_url = str(payload.url)
    try:
        normalized_url = shared_normalize_product_url(raw_url)
    except ValueError as exc:
        issue = UrlIssue(code="invalid_url", message=str(exc))
        return _build_error_response(
            issue,
            status_code=status.HTTP_400_BAD_REQUEST,
            trace_id=trace_id,
            request_logger=request_logger,
            log_extra=_sanitize_invalid_url_log_payload(raw_url),
        )
    
    request_logger = request_logger.bind(url=sanitize_log_data(normalized_url))

    compatibility = shared_check_url_compatibility(
        normalized_url,
        ensure_public_endpoint=_ensure_public_endpoint,    
    )
    if compatibility:
        return _build_error_response(
            compatibility,
            status_code=status.HTTP_400_BAD_REQUEST,
            trace_id=trace_id,
            request_logger=request_logger,
        )
    
    force_refresh = bool(payload.metadata.get("force_refresh")) if payload.metadata else False
    if force_refresh:
        request_logger.info(
            "http_cache_force_refresh",
            url=sanitize_log_data(normalized_url),
            reason="force_refresh_metadata",
        )
    cached_metadata = None
    cache_status = "miss"
    if not force_refresh:
        #Cache HTTP aqui é independente do cache interno do pipeline
        request_logger.info(
            "http_cache_lookup",
            url=sanitize_log_data(normalized_url),
        )
        cached_metadata = get_cached_response(normalized_url)
        if cached_metadata:
            cache_status = "hit"
        if cached_metadata and should_return_not_modified(
            if_none_match=request.headers.get("if-none-match"),
            if_modified_since=parse_if_modified_since(request.headers.get("if-modified-since")),
            metadata=cached_metadata,
        ):
            headers = build_cache_headers(cached_metadata)
            headers["X-MarketScraper-Cache-Status"] = cache_status
            headers[SCRAPER_CONTRACT_VERSION_HEADER] = SCRAPER_CONTRACT_VERSION
            request_logger.info(
                "parse_not_modified",
                url=sanitize_log_data(normalized_url),
                etag=cached_metadata.etag,
                source=cached_metadata.payload.source,
            )
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
        if cached_metadata:
            cache_status = "revalidated"
    else:
        cache_status = "bypass"

    use_case_result = await ParseProduct().execute(
        normalized_url,
        request_logger=request_logger,
        force_refresh=force_refresh,
        trace_id=trace_id,
    )
    if isinstance(use_case_result, ParseProductError):
        if use_case_result.invalidate_cache:
            invalidate_cached_response(normalized_url)
        return _build_error_response(
            use_case_result.issue,
            status_code=use_case_result.http_status,
            trace_id=trace_id,
            request_logger=request_logger,
        )
    if isinstance(use_case_result, ParseProductNoResult):
        return build_no_result_response(
            reason_code=use_case_result.reason_code,
            trace_id=trace_id,
            request_logger=request_logger.bind(url=sanitize_log_data(normalized_url)),
        )
    parse_response = use_case_result.parser_response
    try:
        metadata = store_response(normalized_url, parse_response)
    except Exception as exc:
        metadata = None
        request_logger.warning(
            "http_cache_store_failed",
            url=sanitize_log_data(normalized_url),
            cache_status=cache_status,
            error=sanitize_log_data(str(exc)),
        )
    if metadata:
        request_logger.info(
            "http_cache_stored",
            url=sanitize_log_data(normalized_url),
            etag=metadata.etag,
            source=metadata.payload.source,
            cache_status=cache_status,
        )
        for key, value in build_cache_headers(metadata).items():
            response.headers[key] = value
    #Cabeçalho customizado facilita inspeção de decisões do cache HTTP pelo cliente
    response.headers["X-MarketScraper-Cache-Status"] = cache_status
    response.headers[SCRAPER_CONTRACT_VERSION_HEADER] = SCRAPER_CONTRACT_VERSION
    return parse_response


__all__ = ["router"]
