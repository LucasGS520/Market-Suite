""" Fornece auxiliares para estruturar respostas das rotas do scraper

O módulo mantém a formatação padronizada de erros HTTP, concentra o 
saneamento de campos sensíveis e centraliza traduções de problemas do
pipeline para ``UrlIssue``. Dessa forma as rotas permanecem focadas na
orquestração do fluxo.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from structlog.stdlib import BoundLogger

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.schemas.parse import ParserResponse
from market_scraper.services.synergic_pipeline import PipelineOutcome
from market_scraper.utils.url_validation import UrlIssue


def _sanitize_payload(url: str) -> dict[str, str]:
    """ Normaliza campos sensíveis antes do registro em log """
    #Mantemos o helper isolado para reaproveitar a mesma estratégia de sanitização sempre que o endpoint precisar incluir a URL nos logs.
    return {"url": sanitize_log_data(url)}

def _map_http_download_issue(outcome: PipelineOutcome) -> tuple[UrlIssue, int] | None:
    """ Converte problemas de download em uma ``UrlIssue`` apropriada """
    if any(step.message == "unsupported_by_robots" for step in outcome.steps):
        issue = UrlIssue(
            code="unsupported_by_robots",
            message="O acesso à URL foi bloqueado pelas regras de robots.txt",
        )
        return issue, status.HTTP_403_FORBIDDEN
    return None

def _http_error(
    issue: UrlIssue,
    *,
    status_code: int,
    trace_id: str,
    request_logger: BoundLogger,
    log_extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """ Monta uma resposta JSON padronizada para erros do endpoint """
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
        },
    )

def build_no_result_response(
    *,
    outcome: PipelineOutcome,
    request_logger: BoundLogger,
    trace_id: str,
) -> JSONResponse:
    """ Registra o cenário sem resultado e delega resposta padronizada """
    validation_failures = outcome.context.data.get("validation_failures", [])
    last_failure = validation_failures[-1] if validation_failures else None
    request_logger.warning(
        "parse_no_result",
        url=sanitize_log_data(outcome.context.url),
        source=outcome.context.source,
        error_code="no_result",
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

def build_success_response(
    payload: dict[str, Any],
    *,
    normalized_url: str,
    outcome: PipelineOutcome,
    request_logger: BoundLogger,
    current_price: Decimal,
) -> ParserResponse:
    """ Cria ``ParserResponse`` garantindo consistência de logs """
    response = ParserResponse(
        name=payload.get("name", ""),
        current_price=current_price,
        url=normalized_url,
        source=payload.get("source", outcome.context.source),
    )
    request_logger.info(
        "parse_success",
        url=sanitize_log_data(response.url),
        source=response.source,
    )
    return response


__all__ = [
    "_http_error",
    "_map_http_download_issue",
    "_sanitize_payload",
    "build_no_result_response",
    "build_success_response",
]
