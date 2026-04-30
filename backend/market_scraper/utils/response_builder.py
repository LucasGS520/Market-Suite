""" Construção de respostas HTTP contrato para o endpoint de scraping.

Centraliza: ParserResponse a partir de PostProcessResult e resposta de
erro 422 para no_result.
A rota HTTP permanece casca fina — não constrói payloads diretamente.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from fastapi import status as http_status
from structlog.stdlib import BoundLogger

from shared.schemas import ParserResponse
from shared.schemas.shared_schemas_scraper import (
    SCRAPER_CONTRACT_VERSION,
    SCRAPER_CONTRACT_VERSION_HEADER,
)
from shared.utils.logging_utils import sanitize_log_data

from market_scraper.domain.dtos import PostProcessResult


def build_parser_response(
    result: PostProcessResult,
    *,
    request_logger: BoundLogger,
) -> ParserResponse:
    """Monta ParserResponse a partir de PostProcessResult tipado.

    PostProcessResult já carrega preço como Decimal e telemetria consolidada
    em extra_fields["acquisition"], eliminando re-parsing e merges manuais.
    """
    response = ParserResponse(
        name=result.name or "",
        current_price=result.current_price,
        currency=result.currency,
        availability=result.availability,
        last_status=result.last_status,
        url=result.url,
        source=result.source,
        payload=result.extra_fields or None,
    )
    request_logger.info(
        "parse_success",
        url=sanitize_log_data(str(response.url)),
        source=response.source,
    )
    return response


def build_no_result_response(
    *,
    reason_code: str | None,
    trace_id: str,
    request_logger: BoundLogger,
    log_extra: dict[str, Any] | None = None,
    classification_reason: str | None = None,
) -> JSONResponse:
    """Monta resposta 422 padronizada quando o pipeline não extrai dados úteis.

    Consolida a criação de UrlIssue + log de aviso que estava inline na rota.
    """
    request_logger.warning(
        "parse_no_result",
        reason_code=reason_code,
        classification_reason=classification_reason,
        **(log_extra or {}),
    )
    content: dict[str, Any] = {
        "message": "Não foi possível extrair dados do produto",
        "error_code": "no_result",
        "trace_id": trace_id,
    }
    if classification_reason is not None:
        content["classification_reason"] = classification_reason
    return JSONResponse(
        status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
        headers={SCRAPER_CONTRACT_VERSION_HEADER: SCRAPER_CONTRACT_VERSION},
        content=content,
    )


__all__ = [
    "build_parser_response",
    "build_no_result_response",
]
