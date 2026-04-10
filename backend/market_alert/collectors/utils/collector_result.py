""" Utilitário para normalização de resultados e decisões do coletor.

Centraliza regras de outcome, motivos de ``no_result`` e parsing de payloads
retornados pelo collector. Assim mantemos o módulo de preços focado apenas em
normalização e histórico, evitando responsabilidades misturadas.
"""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import UUID

from shared.schemas.shared_schemas_scraper import ScrapeResult


TEMPORARY_FAILURE_ERROR_CODES = {
    "rate_limit",
    "too_many_requests",
    "timeout",
    "service_unavailable",
    "gateway_timeout",
}
TEMPORARY_FAILURE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}
INVALID_URL_ERRORS_CODES = {
    "too_many_redirects",
    "redirect_loop",
    "invalid_url",
    "unsupported_by_robots",
    "blocked_host",
    "unsupported_protocol",
}
RATE_LIMIT_ERROR_CODES = {"rate_limit", "too_many_requests", "429", "rate_limit_window_exhausted"}

def _resolve_outcome(
    kind: str,
    result: ScrapeResult | None,
    *,
    lock_status: str,
    reason: str | None,
) -> str:
    """ Normaliza o desfecho do coletor para o contrato esperado pelo pipeline """
    if lock_status == "skipped":
        return "no_result"
    
    if reason == "scraping_suspended":
        return "no_result"
    
    if reason == "invalid_payload":
        return "error"
    
    if reason == "missing_target":
        return "no_result"
    
    if reason in {"scraper_error", "unexpected_error"}:
        return "error"
    
    if result is None:
        return "error"
    
    if result.status == "no_result":
        return "no_result"
    
    if result.status == "not_modified":
        return "not_modified"
    
    if result.status == "success":
        return "success"
    
    return "error"

def _resolve_no_result_reason(result: ScrapeResult | None) -> str:
    """ Determina uma razão descritiva para status ``no_result``.

    Distingue explicitamente lock contention, pausa e ausência de alvo para
    que callers possam diferenciar causas operacionais de causas de extração.
    """
    if result is None:
        return "validation"

    error_code = (result.error_code or "").strip().lower()

    if error_code == "lock_skipped":
        return "lock_skipped"

    if error_code in {"paused", "missing_target"}:
        return error_code

    if "robot" in error_code:
        return "robots"

    if error_code in RATE_LIMIT_ERROR_CODES or result.http_status == 429:
        return "rate_limit"

    if error_code in INVALID_URL_ERRORS_CODES:
        return "invalid_url"

    if "timeout" in error_code or result.http_status in {408, 504}:
        return "timeout"

    return "validation"

def _should_schedule_temporary_retry(
    result: ScrapeResult | None,
    reason: str | None,
) -> bool:
    """ Indica se a falha deve gerar backoff e reprocessamento tardio """
    if result is None:
        return False
    
    error_code = (result.error_code or "").strip().lower()
    http_status = result.http_status

    if reason in {"rate_limit", "timeout"}:
        return True
    
    if error_code in INVALID_URL_ERRORS_CODES:
        return False
    
    if error_code == "no_result":
        return False

    if error_code in TEMPORARY_FAILURE_ERROR_CODES:
        return True
    
    if http_status in TEMPORARY_FAILURE_HTTP_STATUSES:
        return True
    
    return False

def _should_block_invalid_url(result: ScrapeResult | None) -> bool:
    """ Indica se o erro deve contar como URL inválida """
    if result is None:
        return False
    error_code = (result.error_code or "").strip().lower()
    return error_code in INVALID_URL_ERRORS_CODES

def _is_rate_limit_error(result: ScrapeResult | None, reason: str | None) -> bool:
    """ Detecta falhas relacionadas a rate limit para aplicar cooldown """
    if reason == "rate_limit":
        return True
    if result is None:
        return False
    error_code = (result.error_code or "").strip().lower()
    return error_code in RATE_LIMIT_ERROR_CODES or result.http_status == 429

def _extract_host(url: str | None) -> str:
    """ Extrai o host de uma URL para uso em logs """
    if not url:
        return "unknown"
    try:
        parsed = urlparse(url)
        return parsed.netloc or "unknown"
    except Exception:
        return "unknown"
    
def _parse_collect_result(collect_result: Any) -> dict[str, Any]:
    """ Normaliza o retorno da task de coleta preservando compatibilidade """
    if isinstance(collect_result, Mapping):
        return dict(collect_result)
    if isinstance(collect_result, str):
        return {"outcome": collect_result, "status": collect_result, "reason": collect_result}
    return {"outcome": "unknown", "status": "unknown", "reason": "unknown"}

def _validate_payload(
    payload: Mapping[str, str | None] | None,
) -> tuple[str, UUID | None, UUID | None, str | None]:
    """ Valida campos mínimos, retornando tipo, IDs e URL 
    
    A validação impede que a tarefa tenta acessar campos ausentes e garante
    que tenhamos um identificador claro para aplicar o lock. Em caso de 
    inconsistências retornamos identificadores nulos para facilitar logs.
    """
    if payload is None:
        return "unknown", None, None, None
    
    competitor_id_value = payload.get("competitor_id")
    monitored_id_value = payload.get("monitored_id")
    url = payload.get("url")

    competitor_id = None
    monitored_id = None

    try:
        competitor_id = UUID(str(competitor_id_value)) if competitor_id_value else None
    except Exception:
        competitor_id = None

    try:
        monitored_id = UUID(str(monitored_id_value)) if monitored_id_value else None
    except Exception:
        monitored_id = None

    kind = "competitor" if competitor_id is not None else "monitored"
    if monitored_id is None and competitor_id is None:
        kind = payload.get("kind", "unknown") or "unknown"

    return kind, monitored_id, competitor_id, url


__all__ = [
    "INVALID_URL_ERRORS_CODES",
    "_resolve_outcome",
    "_resolve_no_result_reason",
    "_should_schedule_temporary_retry",
    "_should_block_invalid_url",
    "_is_rate_limit_error",
    "_extract_host",
    "_parse_collect_result",
    "_validate_payload",
]
