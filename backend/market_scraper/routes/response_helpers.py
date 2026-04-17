""" Fornece auxiliares para estruturar respostas das rotas do scraper

O módulo mantém a formatação padronizada de erros HTTP, concentra o
saneamento de campos sensíveis e centraliza traduções de problemas do
pipeline para ``UrlIssue``. Dessa forma as rotas permanecem focadas na
orquestração do fluxo.

Matriz de decisão do endpoint /scraper/parse
============================================
| outcome.status | payload útil? | anti_bot | Resposta HTTP          |
|----------------|---------------|----------|------------------------|
| success        | sim           | não      | 200 OK (normal)        |
| success        | sim           | sim      | 200 OK (degradado)*    |
| no_result      | —             | —        | 422 no_result          |
| error/timeout  | —             | —        | 4xx/5xx por tipo       |
| —              | —             | bloqueio | 403/429/503/504        |

*sucesso degradado = anti-bot detectado porém nome+preço extraídos com sucesso.
Implementado na Fase 5 do plano de refatoração.

Critério de dado útil (single source of truth): nome + preço, ou nome +
disponibilidade explicitamente falsa. Ver ``has_useful_payload``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from structlog.stdlib import BoundLogger

from shared.schemas import ParserResponse
from shared.schemas.shared_schemas_scraper import SCRAPER_CONTRACT_VERSION, SCRAPER_CONTRACT_VERSION_HEADER
from shared.utils.logging_utils import sanitize_log_data
from shared.utils.url_validation import UrlIssue

from market_scraper.services.synergic_pipeline import PipelineOutcome
from market_scraper.utils.validator import is_useful_payload


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
    if any(step.message == "too_many_redirects" for step in outcome.steps):
        issue = UrlIssue(
            code="too_many_redirects",
            message="A URL entrou em loop de redirecionamento",
        )
        return issue, status.HTTP_422_UNPROCESSABLE_ENTITY
    if any(step.message == "invalid_url" for step in outcome.steps):
        issue = UrlIssue(
            code="invalid_url",
            message="A URL informada é inválida ou usa protocolo não suportado",
        )
        return issue, status.HTTP_422_UNPROCESSABLE_ENTITY
    if any(step.message == "anti_bot_page" for step in outcome.steps):
        issue = UrlIssue(
            code="anti_bot_page",
            message="Página de proteção anti-bot detectada; tente novamente mais tarde",
        )
        return issue, status.HTTP_429_TOO_MANY_REQUESTS
    if any(step.message == "rate_limiter_cooldown" for step in outcome.steps):
        issue = UrlIssue(
            code="rate_limiter_cooldown",
            message="Limite de requisições atingido para este domínio; tente novamente em instantes",
        )
        return issue, status.HTTP_429_TOO_MANY_REQUESTS
    if any(step.message == "playwright_timeout" for step in outcome.steps):
        issue = UrlIssue(
            code="playwright_timeout",
            message="Tempo limite excedido ao renderizar a página com browser",
        )
        return issue, status.HTTP_504_GATEWAY_TIMEOUT
    if any(step.message == "playwright_fetch_error" for step in outcome.steps):
        issue = UrlIssue(
            code="playwright_fetch_error",
            message="Erro ao obter conteúdo via browser; tente novamente",
        )
        return issue, status.HTTP_503_SERVICE_UNAVAILABLE
    if any(step.message in ("pipeline_degraded", "playwright_not_ready") for step in outcome.steps):
        issue = UrlIssue(
            code="pipeline_degraded",
            message="Serviço temporariamente degradado; fallback de browser indisponível",
        )
        return issue, status.HTTP_503_SERVICE_UNAVAILABLE
    return None

def _http_error(
    issue: UrlIssue,
    *,
    status_code: int,
    trace_id: str,
    request_logger: BoundLogger,
    log_extra: dict[str, Any] | None = None,
    suppress_log: bool = False,
) -> JSONResponse:
    """ Monta uma resposta JSON padronizada para erros do endpoint.

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

def _derive_no_result_reason(outcome: PipelineOutcome) -> str:
    """ Deriva motivo explícito quando nenhuma falha de validação foi registrada.

    Distingue três causas: HTML indisponível, domínio sem parser dedicado,
    e parsers executados mas sem dados extraíveis.
    """
    if not outcome.context.html:
        return "html_unavailable"
    if outcome.context.data.get("no_domain_parser"):
        return "no_domain_parser"
    return "no_parser_data"


def build_no_result_response(
    *,
    outcome: PipelineOutcome,
    request_logger: BoundLogger,
    trace_id: str,
) -> JSONResponse:
    """ Registra o cenário sem resultado e delega resposta padronizada """
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
    )
    issue = UrlIssue(code="no_result", message="Não foi possível extrair dados do produto")
    # suppress_log=True porque parse_no_result acima já registrou o evento com contexto completo
    return _http_error(
        issue,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        trace_id=trace_id,
        request_logger=request_logger,
        suppress_log=True,
    )

def _extract_additional_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    """ Remove campos padrão preservando apenas metadados adicionais """
    base_keys = {
        "name",
        "current_price",
        "url",
        "source",
        "marketplace",
        "currency",
        "availability",
        "last_status",
        "etag",
        "not_modified",
    }
    extras = {key: value for key, value in data.items() if key not in base_keys and value is not None}
    return extras or None

def _derive_data_quality(context_data: dict[str, Any]) -> str:
    """ Deriva indicador de qualidade de aquisição a partir do contexto do pipeline.

    Valores possíveis:
        ``"normal"``           — HTTP direto sem anti-bot.
        ``"degraded_anti_bot"`` — Anti-bot detectado mas dados extraídos (sem Playwright).
        ``"browser_fallback"``  — Playwright acionado (com ou sem anti-bot residual).
    """
    if context_data.get("fallback_taken"):
        return "browser_fallback"
    if context_data.get("anti_bot_detected"):
        return "degraded_anti_bot"
    return "normal"


def _extract_acquisition_payload(context_data: dict[str, Any]) -> dict[str, Any] | None:
    """ Expõe telemetria de aquisição de forma aditiva no payload HTTP. """
    acquisition_keys = (
        "layer_used",
        "fallback_taken",
        "classification_reason",
        "http_status",
        "anti_bot_detected",
        "anti_bot_pattern",
        "anti_bot_bypassed",
    )
    if not any(key in context_data for key in acquisition_keys):
        return None

    return {
        "layer_used": context_data.get("layer_used"),
        "fallback_taken": bool(context_data.get("fallback_taken", False)),
        "classification_reason": context_data.get("classification_reason"),
        "http_status": context_data.get("http_status"),
        "anti_bot_detected": bool(context_data.get("anti_bot_detected", False)),
        "anti_bot_pattern": context_data.get("anti_bot_pattern"),
        "anti_bot_bypassed": bool(context_data.get("anti_bot_bypassed", False)),
        "data_quality": _derive_data_quality(context_data),
    }

def _merge_availability_and_status(
    payload: dict[str, Any],
    context_data: dict[str, Any],
) -> dict[str, Any]:
    """ Aplica precedência explícita para disponibilidade e último status """
    merged = dict(payload)
    inferred_availability = context_data.get("availability_inferred")
    if merged.get("availability") is None and inferred_availability is not None:
        merged["availability"] = inferred_availability

    inferred_last_status = context_data.get("last_status_inferred")
    if not merged.get("last_status") and inferred_last_status:
        merged["last_status"] = inferred_last_status

    context_last_status = context_data.get("last_status")
    if not merged.get("last_status") and context_last_status:
        merged["last_status"] = context_last_status
    return merged

def build_success_response(
    payload: dict[str, Any],
    *,
    normalized_url: str,
    outcome: PipelineOutcome,
    request_logger: BoundLogger,
    current_price: Decimal | None,
) -> ParserResponse:
    """ Cria ``ParserResponse`` garantindo consistência de logs """
    merged_payload = _merge_availability_and_status(payload, outcome.context.data)
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
        url=sanitize_log_data(response.url),
        source=response.source,
    )
    return response


def has_useful_payload(payload: dict) -> bool:
    """Verifica se um payload contém dado útil (nome + preço ou indisponível explícito).

    Delega para ``is_useful_payload`` do módulo ``validator`` — fonte canônica única.
    """
    return is_useful_payload(payload)


__all__ = [
    "_http_error",
    "_map_http_download_issue",
    "_extract_additional_payload",
    "_extract_acquisition_payload",
    "_merge_availability_and_status",
    "_sanitize_payload",
    "build_no_result_response",
    "build_success_response",
    "has_useful_payload",
]
