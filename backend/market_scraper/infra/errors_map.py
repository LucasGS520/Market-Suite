""" Taxonomia canônica de erros internos → código HTTP + error_code externo.

Local único de decisão para todos os mapeamentos de erro do pipeline.
Cada entrada define (error_code_externo, mensagem_pt_br, http_status).

Uso:

    from market_scraper.infra.errors_map import map_collection_error

    result = map_collection_error("anti_bot_page")
    if result:
        issue, status = result
"""

from __future__ import annotations

from fastapi import status as http_status

from shared.utils.url_validation import UrlIssue


# ── Taxonomia de erros de coleta ────────────────────────────────────────────
# Chave  = error_code interno (CollectedDocument.error_code)
# Valor  = (error_code_externo, mensagem, http_status)

COLLECTION_ERROR_MAP: dict[str, tuple[str, str, int]] = {
    # ── Configuração incompleta ──────────────────────────────────────────
    "missing_proxy_config": (
        "missing_proxy_config",
        "Coleta requer proxy ativo neste ambiente; configure SCRAPER_PROXY_URLS",
        http_status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    # ── Anti-bot / rate limit ────────────────────────────────────────────
    "anti_bot_blocked": (
        "anti_bot_blocked",
        "Bloqueio anti-bot terminal detectado; troque de identidade antes de nova tentativa",
        http_status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    "anti_bot_page": (
        "anti_bot_page",
        "Página de proteção anti-bot detectada; tente novamente mais tarde",
        http_status.HTTP_429_TOO_MANY_REQUESTS,
    ),
    "rate_limiter_cooldown": (
        "rate_limiter_cooldown",
        "Limite de requisições atingido para este domínio; tente novamente em instantes",
        http_status.HTTP_429_TOO_MANY_REQUESTS,
    ),
    # ── Redirecionamento / URL inválida ──────────────────────────────────
    "too_many_redirects": (
        "too_many_redirects",
        "A URL entrou em loop de redirecionamento",
        http_status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
    "invalid_url": (
        "invalid_url",
        "A URL informada é inválida ou usa protocolo não suportado",
        http_status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
    # ── Browser (Playwright) ─────────────────────────────────────────────
    "playwright_timeout": (
        "playwright_timeout",
        "Tempo limite excedido ao renderizar a página com browser",
        http_status.HTTP_504_GATEWAY_TIMEOUT,
    ),
    "playwright_fetch_error": (
        "playwright_fetch_error",
        "Erro ao obter conteúdo via browser; tente novamente",
        http_status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    "playwright_not_ready": (
        "pipeline_degraded",
        "Serviço temporariamente degradado; fallback de browser indisponível",
        http_status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    "pipeline_degraded": (
        "pipeline_degraded",
        "Serviço temporariamente degradado; fallback de browser indisponível",
        http_status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
}

# Resposta padrão quando o error_code não está na taxonomia.
_UPSTREAM_ERROR_DEFAULT = (
    UrlIssue(
        code="upstream_error",
        message="Falha ao obter conteúdo da URL; tente novamente",
    ),
    http_status.HTTP_503_SERVICE_UNAVAILABLE,
)


def map_collection_error(error_code: str | None) -> tuple[UrlIssue, int]:
    """Mapeia error_code interno → (UrlIssue, http_status) para transporte HTTP.

    Sempre retorna um par válido; usa upstream_error/503 como fallback para
    códigos desconhecidos.
    """
    code = error_code or "upstream_error"
    mapping = COLLECTION_ERROR_MAP.get(code)
    if mapping:
        issue_code, message, status_code = mapping
        return UrlIssue(code=issue_code, message=message), status_code
    return _UPSTREAM_ERROR_DEFAULT


#Erros que indicam problema de conteúdo (não infra transitória) → invalidam cache.
CACHE_INVALIDATING_ERROR_CODES: frozenset[str] = frozenset(
    {"anti_bot_page", "too_many_redirects", "invalid_url"}
)


__all__ = [
    "CACHE_INVALIDATING_ERROR_CODES",
    "COLLECTION_ERROR_MAP",
    "map_collection_error",
]
