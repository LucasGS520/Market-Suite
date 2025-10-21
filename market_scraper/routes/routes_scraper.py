""" Define as rotas responsáveis por acionar o pipeline de scraping 

O módulo concentra o endpoint ``/parse`` responsável por executar o
pipeline sequencial de scraping.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, status
from fastapi.responses import JSONResponse
import structlog
from structlog.stdlib import BoundLogger

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.schemas.parse import ErrorResponse, ParseRequest, ParserResponse
from market_scraper.services.services_scraper_common import run_pipeline
from market_scraper.services.synergic_pipeline import PipelineTimeoutError
from market_scraper.utils.price import parse_price_str
from market_scraper.utils.url_validation import UrlIssue, check_url_compatibility, normalize_product_url


logger = structlog.get_logger("routes_scraper")

router = APIRouter(tags=["scraper"])

def _http_error(
    issue: UrlIssue,
    *,
    status_code: int,
    trace_id: str,
    request_logger: BoundLogger,
    log_extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """ Cria uma resposta JSON padronizada para os erros do endpoint
    
    O helper adiciona ``trace_id`` ao payload, serializa ``error_code`` 
    e garante que os logs tenham contexto suficiente para rastrear falha
    """
    log_payload = dict(log_extra or {})
    request_logger.warning(
        "parse_error",
        error_code=issue.code,
        message=issue.message,
        **log_payload,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "message": issue.message,
            "error_code": issue.code,
            "trace_id": trace_id,
        }
    )

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
    #Ligamos o identificador para garantir correlação entre respostas e logs estruturados
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
            log_extra={"url": sanitize_log_data(payload.url)},
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
        #Mantemos a URL fornecida pelo usuário para garantir previsibilidade em cache e métricas
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
    
    #Identifica se alguma etapa encerrou por causa do robots.txt e devolve o código especializado
    if any(step.message == "unsupported_by_robots" for step in outcome.steps):
        issue = UrlIssue(
            code="unsupported_by_robots",
            message="O acesso à URL foi bloqueado pelas regras de robots.txt",
        )
        return _http_error(
            issue,
            status_code=status.HTTP_403_FORBIDDEN,
            trace_id=trace_id,
            request_logger=request_logger,
        )

    if outcome.status != "success" or not outcome.payload:
        validation_failures = outcome.context.data.get("validation_failures", [])
        last_failure = validation_failures[-1] if validation_failures else None
        request_logger.warning(
            "parse_no_result",
            url=sanitize_log_data(normalized_url),
            source=outcome.context.source,
            reason_code=last_failure.get("reason_code") if last_failure else None,
            reason_message=last_failure.get("reason_message") if last_failure else None,
            step=last_failure.get("step") if last_failure else None,
            parser_name=last_failure.get("parser_name") if last_failure else None,
            dump_path=last_failure.get("dump_path") if last_failure else None,
        )
        issue = UrlIssue(code="no_result", message="Não foi possível extrair dados do produto")
        return _http_error(
            issue,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            trace_id=trace_id,
            request_logger=request_logger,
        )
    
    payload = outcome.payload

    try:
        price = parse_price_str(payload.get("current_price"), normalized_url)
    except ValueError as exc:
        issue = UrlIssue(code="invalid_price", message=str(exc))
        return _http_error(
            issue,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            trace_id=trace_id,
            request_logger=request_logger,
        )
    
    response = ParserResponse(
        name=payload.get("name", ""),
        current_price=price,
        url=normalized_url,
        source=payload.get("source", outcome.context.source),
    )
    request_logger.info(
        "parse_success",
        url=sanitize_log_data(response.url),
        source=response.source,
    )
    return response

__all__ = ["router"]
