"""Construção de respostas HTTP finais a partir dos dados do pipeline.

Responsabilidade única: montar ParserResponse e JSONResponse de no-result
a partir de dados já mapeados. Inclui price parsing — mantendo a rota
como casca fina sem lógica de negócio inline.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi.responses import JSONResponse
from structlog.stdlib import BoundLogger

from shared.schemas import ParserResponse
from shared.utils.logging_utils import sanitize_log_data
from shared.utils.url_validation import UrlIssue

from market_scraper.services.synergic_pipeline import PipelineOutcome
from market_scraper.utils.price import parse_price_str
from market_scraper.utils.validator import is_useful_payload

from market_scraper.routes.error_mapper import _http_error
from market_scraper.routes.response_mapper import (
    _derive_no_result_reason,
    _extract_acquisition_payload,
    _extract_additional_payload,
    _merge_availability_and_status,
)


def has_useful_payload(payload: dict) -> bool:
    """Verifica se um payload contém dado útil (nome+preço ou indisponível explícito).

    Delega para is_useful_payload do módulo validator — fonte canônica única.
    """
    return is_useful_payload(payload)


def build_success_response(
    payload: dict[str, Any],
    *,
    normalized_url: str,
    outcome: PipelineOutcome,
    request_logger: BoundLogger,
) -> ParserResponse:
    """Cria ParserResponse garantindo consistência de logs.

    O price parsing foi movido aqui para manter a rota livre de lógica
    de negócio. A rota passa o payload bruto e recebe um ParserResponse pronto.
    """
    merged_payload = _merge_availability_and_status(payload, outcome.context.data)

    price_value = merged_payload.get("current_price")
    current_price: Decimal | None = None
    if price_value is not None:
        try:
            current_price = parse_price_str(price_value, normalized_url)
        except ValueError:
            current_price = None

    extra_payload = _extract_additional_payload(merged_payload) or {}
    acquisition_payload = _extract_acquisition_payload(outcome.context.data)
    if acquisition_payload is not None:
        extra_payload["acquisition"] = acquisition_payload

    response = ParserResponse(
        name=merged_payload.get("name", ""),
        current_price=current_price,
        currency=merged_payload.get("currency"),
        availability=merged_payload.get("availability"),
        last_status=merged_payload.get("last_status"),
        url=normalized_url,
        source=merged_payload.get("source")
        or merged_payload.get("marketplace")
        or outcome.context.source,
        payload=extra_payload or None,
    )
    request_logger.info(
        "parse_success",
        url=sanitize_log_data(str(response.url)),
        source=response.source,
    )
    return response


def build_no_result_response(
    *,
    outcome: PipelineOutcome,
    request_logger: BoundLogger,
    trace_id: str,
) -> JSONResponse:
    """Registra o cenário sem resultado e delega resposta padronizada."""
    validation_failures = outcome.context.data.get("validation_failures", [])
    last_failure = validation_failures[-1] if validation_failures else None
    reason_code = (
        last_failure.get("reason_code") if last_failure
        else _derive_no_result_reason(outcome)
    )
    request_logger.warning(
        "parse_no_result",
        url=sanitize_log_data(outcome.context.url),
        source=outcome.context.source,
        error_code="no_result",
        reason_code=reason_code,
        reason_message=last_failure.get("reason_message") if last_failure else None,
        step=last_failure.get("step") if last_failure else None,
        parser_name=last_failure.get("parser_name") if last_failure else None,
        dump_path=last_failure.get("dump_path") if last_failure else None,
        anti_bot_pattern=outcome.context.data.get("anti_bot_pattern"),
        challenge_residual=outcome.context.data.get("challenge_residual"),
        parser_attempts=len(validation_failures),
    )
    issue = UrlIssue(code="no_result", message="Não foi possível extrair dados do produto")
    return _http_error(
        issue,
        status_code=422,
        trace_id=trace_id,
        request_logger=request_logger,
        suppress_log=True,
    )


__all__ = [
    "build_no_result_response",
    "build_success_response",
    "has_useful_payload",
]
