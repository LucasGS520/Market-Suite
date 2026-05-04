"""Enums de domínio do market_scraper."""

from __future__ import annotations

from enum import Enum


class ClassificationReason(str, Enum):
    """Razões canônicas de classificação de resposta HTTP.

    Subclasse de ``str`` para compatibilidade com campos ``str | None`` existentes
    sem quebrar comparações ou serialização JSON.

    Cada constante corresponde a exatamente um motivo de decisão do pipeline;
    o mesmo erro sempre produz o mesmo valor (determinismo garantido por
    ``crawlee_runtime.py``).
    """

    # ── Erros de transporte (sem status HTTP) ─────────────────────────────
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    NETWORK_ERROR = "network_error"

    # ── Erros de URL / redirect ────────────────────────────────────────────
    TOO_MANY_REDIRECTS = "too_many_redirects"
    INVALID_URL = "invalid_url"

    # ── Status HTTP de rejeição ────────────────────────────────────────────
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    ACCESS_DENIED = "access_denied"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"

    # ── Qualidade do HTML (resposta 2xx) ───────────────────────────────────
    HTML_EMPTY = "html_empty"
    HTML_VALID = "html_valid"
    HTML_WITHOUT_PRODUCT_SIGNALS = "html_without_product_signals"

    # ── Anti-bot ───────────────────────────────────────────────────────────
    ANTI_BOT_PAGE = "anti_bot_page"
    ANTI_BOT_DEGRADED = "anti_bot_degraded"
    ANTI_BOT_BLOCKED = "anti_bot_blocked"   # bloqueio terminal — sem retry com mesma identidade

    # ── Browser outcomes ───────────────────────────────────────────────────
    BROWSER_TIMEOUT = "browser_timeout"
    BROWSER_NOT_AVAILABLE = "browser_not_available"
    BROWSER_FETCH_FAILED = "browser_fetch_failed"
    BROWSER_FETCH_SUCCESS = "browser_fetch_success"


__all__ = ["ClassificationReason"]
