""" Utilitário para normalização de resultados e decisões do coletor.

Centraliza regras de outcome, motivos de ``no_result`` e parsing de payloads
retornados pelo collector. Assim mantemos o módulo de preços focado apenas em
normalização e histórico, evitando responsabilidades misturadas.
"""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import UUID

from shared.schemas.shared_schemas_scraper import SCRAPER_ALLOWED_ERROR_CODES, ScrapeResult
from shared.schemas.collection_catalog import (
    OUTCOME_ERROR,
    OUTCOME_NOT_MODIFIED,
    OUTCOME_NO_RESULT,
    OUTCOME_SUCCESS,
    REASON_HTTP_429,
    REASON_CHALLENGE_DETECTED,
    REASON_NAVIGATION_TIMEOUT,
    REASON_DOM_NOT_READY,
    REASON_SELECTOR_MISSING,
    REASON_PARSE_PRICE_FAILED,
    REASON_UNEXPECTED_CONTENT_TYPE,
    REASON_SCRAPER_UNAVAILABLE,
    REASON_INVALID_URL,
    REASON_BLOCKED_HOST,
    REASON_ROBOTS_DISALLOWED,
    REASON_INVALID_PAYLOAD,
    REASON_SCRAPER_ERROR,
    REASON_UNEXPECTED_ERROR,
    REASON_PARSE_EMPTY,
    REASON_LOCK_SKIPPED,
    REASON_SCRAPING_SUSPENDED,
    REASON_MISSING_TARGET,
    REASON_PAUSED,
    NEUTRAL_REASONS,
    REASON_IS_RETRYABLE,
)

#Códigos de erro vindos do scraper que indicam falha transitória de infra.
# Nota: estas são strings de error_code do scraper (namespace do scraper), distintas dos catalog reasons emitidos pelo coletor.
TEMPORARY_FAILURE_ERROR_CODES = {
    "rate_limit",
    "too_many_requests",
    "timeout",
    "pipeline_timeout",
    "service_unavailable",
    "gateway_timeout",
}
TEMPORARY_FAILURE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}

#Códigos de error_code do scraper que indicam URL estruturalmente inválida.
INVALID_URL_ERRORS_CODES = {
    "too_many_redirects",
    "redirect_loop",
    "invalid_url",
    "unsupported_by_robots",
    "blocked_host",
    "unsupported_protocol",
}

#Códigos de error_code do scraper que indicam rate limit / anti-bot.
RATE_LIMIT_ERROR_CODES = {"rate_limit", "too_many_requests", "429", "rate_limit_window_exhausted"}

#Matriz contratual do scraper -> reason semântico do coletor.
#Deve cobrir exatamente os error_codes documentados em shared_schemas_scraper.py.
SCRAPER_CONTRACT_ERROR_CODE_TO_REASON: dict[str, str] = {
    "invalid_url": REASON_INVALID_URL,
    "blocked_host": REASON_BLOCKED_HOST,
    "unsupported_by_robots": REASON_ROBOTS_DISALLOWED,
    "too_many_redirects": REASON_INVALID_URL,
    "anti_bot_page": REASON_CHALLENGE_DETECTED,
    "no_result": REASON_PARSE_EMPTY,
    "pipeline_timeout": REASON_NAVIGATION_TIMEOUT,
}

#Compatibilidade retroativa para error_codes legados/operacionais ainda possíveis no cliente ou em integrações antigas, sempre convergindo para o catálogo.
SCRAPER_LEGACY_ERROR_CODE_TO_REASON: dict[str, str] = {
    #Rate limit
    "rate_limit": REASON_HTTP_429,
    "too_many_requests": REASON_HTTP_429,
    "429": REASON_HTTP_429,
    "rate_limit_window_exhausted": REASON_HTTP_429,
    #Timeout / navegação
    "timeout": REASON_NAVIGATION_TIMEOUT,
    "navigation_timeout": REASON_NAVIGATION_TIMEOUT,
    "html_unavailable": REASON_NAVIGATION_TIMEOUT,
    "gateway_timeout": REASON_NAVIGATION_TIMEOUT,
    #DOM / estrutura de parse
    "dom_not_ready": REASON_DOM_NOT_READY,
    "selector_missing": REASON_SELECTOR_MISSING,
    "no_domain_parser": REASON_SELECTOR_MISSING,
    "parse_price_failed": REASON_PARSE_PRICE_FAILED,
    "unexpected_content_type": REASON_UNEXPECTED_CONTENT_TYPE,
    #URL estruturalmente inválida
    "unsupported_protocol": REASON_INVALID_URL,
    "redirect_loop": REASON_INVALID_URL,
    #Scraper indisponível
    "service_unavailable": REASON_SCRAPER_UNAVAILABLE,
    "scraper_error": REASON_SCRAPER_ERROR,
    "validation_error": REASON_PARSE_PRICE_FAILED,
    #Domínio vazio
    "no_parser_data": REASON_PARSE_EMPTY,
}

SCRAPER_ERROR_CODE_TO_REASON: dict[str, str] = {
    **SCRAPER_CONTRACT_ERROR_CODE_TO_REASON,
    **SCRAPER_LEGACY_ERROR_CODE_TO_REASON,
}

UNMAPPED_SCRAPER_CONTRACT_ERROR_CODES = frozenset(
    set(SCRAPER_ALLOWED_ERROR_CODES) - set(SCRAPER_CONTRACT_ERROR_CODE_TO_REASON)
)

def _has_source_integrity(result: ScrapeResult | None) -> bool:
    """ Indica se a origem é confiável para emitir not_modified.

    Fase 2: derivado implicitamente — not_modified só chega via HTTP 304
    (ScrapeResult construído com status='not_modified' pelo services layer).
    Campo explícito source_integrity será adicionado em versão futura do payload.
    """
    if result is None:
        return False
    return result.status == OUTCOME_NOT_MODIFIED

def _resolve_outcome(
    kind: str,
    result: ScrapeResult | None,
    *,
    lock_status: str,
    reason: str | None,
) -> str:
    """ Normaliza o desfecho do coletor para o contrato esperado pelo pipeline.

    Regras de emissão:
    - not_modified: somente quando source_integrity for verdadeiro (HTTP 304 íntegro).
    - no_result: somente para ausência operacional/legítima via reason neutro.
    - error: qualquer falha técnica tipada.
    - success: coleta com persistência e dados mínimos válidos.
    """
    if lock_status == "skipped":
        return OUTCOME_NO_RESULT

    if reason == REASON_SCRAPING_SUSPENDED:
        return OUTCOME_NO_RESULT

    if reason == REASON_INVALID_PAYLOAD:
        return OUTCOME_ERROR

    if reason == REASON_MISSING_TARGET:
        return OUTCOME_NO_RESULT

    if reason in {REASON_SCRAPER_ERROR, REASON_UNEXPECTED_ERROR}:
        return OUTCOME_ERROR

    if result is None:
        return OUTCOME_ERROR

    if result.status == OUTCOME_NO_RESULT:
        return OUTCOME_NO_RESULT

    if result.status == OUTCOME_NOT_MODIFIED:
        #Guarda de source_integrity: not_modified só é emitido com origem íntegra.
        if _has_source_integrity(result):
            return OUTCOME_NOT_MODIFIED
        return OUTCOME_ERROR

    if result.status == OUTCOME_SUCCESS:
        return OUTCOME_SUCCESS

    return OUTCOME_ERROR

def _resolve_reason_from_result(result: ScrapeResult | None) -> str | None:
    """ Deriva catalog reason a partir do ScrapeResult.

    Cobre todos os status (error, no_result, etc.) e usa SCRAPER_ERROR_CODE_TO_REASON
    para emitir reasons tipados do catálogo. Retorna None quando não há informação
    suficiente para determinar o reason.
    """
    if result is None:
        return None

    error_code = (result.error_code or "").strip().lower()
    if not error_code:
        return None

    #Reasons neutros passam direto (já são catalog-aware por construção no task)
    if error_code in NEUTRAL_REASONS:
        return error_code

    #Mapeamento direto do error_code do scraper para catalog reason
    catalog_reason = SCRAPER_ERROR_CODE_TO_REASON.get(error_code)
    if catalog_reason:
        return catalog_reason

    #Fallback por HTTP status quando error_code não está no mapeamento
    http_status = result.http_status
    if http_status == 429:
        return REASON_HTTP_429
    if http_status in {408, 504}:
        return REASON_NAVIGATION_TIMEOUT
    if http_status in {400, 403, 422}:
        return REASON_PARSE_PRICE_FAILED

    return None


def _resolve_no_result_reason(result: ScrapeResult | None) -> str:
    """ Determina o reason para resultados no_result (operacionais/neutros).

    Delega para _resolve_reason_from_result() e aplica fallback para garantir
    compatibilidade com callers que esperam string não-nula.
    """
    reason = _resolve_reason_from_result(result)
    return reason or REASON_PARSE_EMPTY

def _should_schedule_temporary_retry(
    result: ScrapeResult | None,
    reason: str | None,
) -> bool:
    """ Indica se a falha deve gerar backoff e reprocessamento tardio.

    Prioridade de decisão:
    1. Reasons neutros (lock, pausa, inativo) → nunca retry temporário.
    2. Catalog reason presente → usa REASON_IS_RETRYABLE como fonte de verdade.
    3. Fallback por error_code do scraper e HTTP status (compatibilidade retroativa).
    """
    if result is None:
        return False

    #Reasons neutros não devem gerar retry — não são falhas de produto
    if reason in NEUTRAL_REASONS:
        return False

    #Catalog reason presente: usa tabela de retryabilidade como fonte de verdade
    if reason is not None and reason in REASON_IS_RETRYABLE:
        return REASON_IS_RETRYABLE[reason]

    #Fallback por error_code do scraper (compatibilidade com resultados sem reason tipado)
    error_code = (result.error_code or "").strip().lower()
    http_status = result.http_status

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
    #Aceita tanto o catalog reason tipado quanto o legacy string "rate_limit"
    if reason in {REASON_HTTP_429, REASON_CHALLENGE_DETECTED, "rate_limit"}:
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
    "SCRAPER_CONTRACT_ERROR_CODE_TO_REASON",
    "SCRAPER_ERROR_CODE_TO_REASON",
    "UNMAPPED_SCRAPER_CONTRACT_ERROR_CODES",
    "_has_source_integrity",
    "_resolve_outcome",
    "_resolve_reason_from_result",
    "_resolve_no_result_reason",
    "_should_schedule_temporary_retry",
    "_should_block_invalid_url",
    "_is_rate_limit_error",
    "_extract_host",
    "_parse_collect_result",
    "_validate_payload",
]
