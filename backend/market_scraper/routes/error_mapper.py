"""Mapeamento de erros do pipeline para respostas HTTP padronizadas.

Responsabilidade única: converter problemas internos (UrlIssue, mensagens
de step) em JSONResponse com schema ErrorResponse e status HTTP correto.
"""

from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from structlog.stdlib import BoundLogger

from shared.schemas.shared_schemas_scraper import (
    SCRAPER_CONTRACT_VERSION,
    SCRAPER_CONTRACT_VERSION_HEADER,
)
from shared.utils.logging_utils import sanitize_log_data
from shared.utils.url_validation import UrlIssue

from market_scraper.services.synergic_pipeline import PipelineOutcome


def _http_error(
    issue: UrlIssue,
    *,
    status_code: int,
    trace_id: str,
    request_logger: BoundLogger,
    log_extra: dict[str, Any] | None = None,
    suppress_log: bool = False,
) -> JSONResponse:
    """Monta resposta JSON padronizada para erros do endpoint.

    suppress_log=True omite o log interno — usar quando o caller já registrou
    um log mais detalhado para o mesmo evento (evita entradas duplicadas).
    """
    if not suppress_log:
        log_payload = dict(log_extra or {})
        request_logger.warning(
            "parse_error",
            error_code=issue.code,
            http_status=status_code,
            message=issue.message,
            **log_payload,
        )

    return JSONResponse(
        status_code=status_code,
        headers={
            SCRAPER_CONTRACT_VERSION_HEADER: SCRAPER_CONTRACT_VERSION,
        },
        content={
            "message": issue.message,
            "error_code": issue.code,
            "trace_id": trace_id,
        },
    )


def _map_http_download_issue(outcome: PipelineOutcome) -> tuple[UrlIssue, int] | None:
    """Converte problemas de download em uma UrlIssue apropriada."""
    if any(step.message == "unsupported_by_robots" for step in outcome.steps):
        return UrlIssue(
            code="unsupported_by_robots",
            message="O acesso à URL foi bloqueado pelas regras de robots.txt",
        ), status.HTTP_403_FORBIDDEN

    if any(step.message == "too_many_redirects" for step in outcome.steps):
        return UrlIssue(
            code="too_many_redirects",
            message="A URL entrou em loop de redirecionamento",
        ), status.HTTP_422_UNPROCESSABLE_ENTITY

    if any(step.message == "invalid_url" for step in outcome.steps):
        return UrlIssue(
            code="invalid_url",
            message="A URL informada é inválida ou usa protocolo não suportado",
        ), status.HTTP_422_UNPROCESSABLE_ENTITY

    if any(step.message == "anti_bot_page" for step in outcome.steps):
        return UrlIssue(
            code="anti_bot_page",
            message="Página de proteção anti-bot detectada; tente novamente mais tarde",
        ), status.HTTP_429_TOO_MANY_REQUESTS

    if any(step.message == "rate_limiter_cooldown" for step in outcome.steps):
        return UrlIssue(
            code="rate_limiter_cooldown",
            message="Limite de requisições atingido para este domínio; tente novamente em instantes",
        ), status.HTTP_429_TOO_MANY_REQUESTS

    if any(step.message == "playwright_timeout" for step in outcome.steps):
        return UrlIssue(
            code="playwright_timeout",
            message="Tempo limite excedido ao renderizar a página com browser",
        ), status.HTTP_504_GATEWAY_TIMEOUT

    if any(step.message == "playwright_fetch_error" for step in outcome.steps):
        return UrlIssue(
            code="playwright_fetch_error",
            message="Erro ao obter conteúdo via browser; tente novamente",
        ), status.HTTP_503_SERVICE_UNAVAILABLE

    if any(step.message in ("pipeline_degraded", "playwright_not_ready") for step in outcome.steps):
        return UrlIssue(
            code="pipeline_degraded",
            message="Serviço temporariamente degradado; fallback de browser indisponível",
        ), status.HTTP_503_SERVICE_UNAVAILABLE

    return None


__all__ = ["_http_error", "_map_http_download_issue"]
