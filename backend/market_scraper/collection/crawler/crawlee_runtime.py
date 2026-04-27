""" Runtime de coleta — coordena HTTP e browser em fluxo determinístico.

CrawleeRuntime encapsula o lifecycle completo de uma operação de coleta:
    1. Tenta HTTP via HttpCollector (curl_cffi)
    2. Classifica resultado via ResponseClassifierPolicy
    3. Escala para browser via BrowserCollector quando necessário
    4. Retorna CollectedDocument fechado com telemetria completa

Projetado como adaptador fino: não reimplementa fingerprinting, pool de browsers
ou retry policy — delega essas funções aos coletores concretos e à política.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import httpx
import structlog

from market_scraper.collection.collectors.browser_collector import PlaywrightBrowserCollector
from market_scraper.collection.collectors.http_collector import CurlCFFIHttpCollector
from market_scraper.collection.dto.collected_document import CollectedDocument
from market_scraper.collection.dto.collection_attempt import CollectionAttempt
from market_scraper.collection.policy import CollectionPolicyAction, ResponseClassifierPolicy
from market_scraper.services.response_classifier import detect_anti_bot_pattern
from market_scraper.infra.browser.playwright_pool import (
    PlaywrightFetchError,
    PlaywrightPoolNotReadyError,
    PlaywrightTimeoutError,
)

if TYPE_CHECKING:
    from market_scraper.collection.collectors.protocols import BrowserCollector, HttpCollector

logger = structlog.get_logger("crawlee_runtime")


class CrawleeRuntime:
    """ Orquestra coleta HTTP → browser com política de decisão determinística.

    Stateless após construção — pode ser instanciado uma vez por processo e
    compartilhado entre requisições concorrentes sem risco de estado mutável.
    """

    def __init__(
        self,
        http_collector: HttpCollector | None = None,
        browser_collector: BrowserCollector | None = None,
        policy: ResponseClassifierPolicy | None = None,
        *,
        http_timeout: float = 15.0,
        browser_timeout: float = 30.0,
    ) -> None:
        self._http = http_collector or CurlCFFIHttpCollector()
        self._browser = browser_collector or PlaywrightBrowserCollector()
        self._policy = policy or ResponseClassifierPolicy()
        self._http_timeout = http_timeout
        self._browser_timeout = browser_timeout

    async def fetch_with_fallback(
        self,
        url: str,
        *,
        domain: str | None = None,
        http_timeout: float | None = None,
        browser_timeout: float | None = None,
    ) -> CollectedDocument:
        """ Obtém HTML com fallback automático HTTP → browser conforme política.

        Args:
            url: URL canônica do produto.
            domain: Hostname para reutilização de sessão persistente no browser.
            http_timeout: Override do timeout HTTP em segundos.
            browser_timeout: Override do timeout browser em segundos.

        Returns:
            CollectedDocument fechado com HTML (ou None em falha) e telemetria completa.
        """
        t_start = time.monotonic()
        ts = time.time()
        http_to = http_timeout if http_timeout is not None else self._http_timeout
        browser_to = browser_timeout if browser_timeout is not None else self._browser_timeout
        attempts: list[CollectionAttempt] = []

        # ── Tentativa HTTP primária ───────────────────────────────────────────
        html_http: str | None = None
        http_status: int | None = None
        http_error: Exception | None = None
        http_error_code: str | None = None
        t_http = time.monotonic()

        try:
            html_http = await self._http.fetch(url, timeout=http_to)
            http_status = 200
        except httpx.TooManyRedirects as exc:
            http_error = exc
            http_error_code = "too_many_redirects"
        except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
            http_error = exc
            http_error_code = "invalid_url"
        except httpx.HTTPStatusError as exc:
            http_error = exc
            http_status = exc.response.status_code
        except Exception as exc:  # noqa: BLE001
            http_error = exc

        http_ms = (time.monotonic() - t_http) * 1000

        # Erros de URL/redirect são fatais — sem classificador, sem browser
        if http_error_code in ("too_many_redirects", "invalid_url"):
            attempts.append(CollectionAttempt(
                layer="http",
                status="failure",
                error_code=http_error_code,
                duration_ms=http_ms,
                reason=http_error_code,
            ))
            return CollectedDocument(
                html=None,
                http_status=http_status,
                headers={},
                layer_used="http",
                fallback_taken=False,
                anti_bot_detected=False,
                anti_bot_pattern=None,
                timestamp=ts,
                duration_ms=(time.monotonic() - t_start) * 1000,
                attempts=tuple(attempts),
                error_code=http_error_code,
                classification_reason=http_error_code,
                anti_bot_bypassed=False,
            )

        decision = self._policy.classify(
            http_status=http_status,
            html=html_http,
            error=http_error,
        )

        anti_bot_pattern: str | None = decision.telemetry.get("anti_bot_pattern")
        anti_bot_detected = bool(
            anti_bot_pattern or decision.telemetry.get("anti_bot_detected", False)
        )

        # ── Aceito via HTTP ───────────────────────────────────────────────────
        if decision.action == CollectionPolicyAction.ACCEPT:
            attempts.append(CollectionAttempt(
                layer="http",
                status="success",
                error_code=None,
                duration_ms=http_ms,
                reason=decision.reason,
            ))
            return CollectedDocument(
                html=html_http,
                http_status=http_status,
                headers={},
                layer_used="http",
                fallback_taken=False,
                anti_bot_detected=anti_bot_detected,
                anti_bot_pattern=anti_bot_pattern,
                timestamp=ts,
                duration_ms=(time.monotonic() - t_start) * 1000,
                attempts=tuple(attempts),
                error_code=None,
                classification_reason=decision.reason,
                anti_bot_bypassed=False,
            )

        # ── Produto indisponível — sem acionar browser ─────────────────────
        if decision.action == CollectionPolicyAction.STOP_UNAVAILABLE:
            unavail_code = f"http_{http_status}_unavailable"
            attempts.append(CollectionAttempt(
                layer="http",
                status="failure",
                error_code=unavail_code,
                duration_ms=http_ms,
                reason=decision.reason,
            ))
            return CollectedDocument(
                html=None,
                http_status=http_status,
                headers={},
                layer_used="http",
                fallback_taken=False,
                anti_bot_detected=False,
                anti_bot_pattern=None,
                timestamp=ts,
                duration_ms=(time.monotonic() - t_start) * 1000,
                attempts=tuple(attempts),
                error_code=unavail_code,
                classification_reason=decision.reason,
                anti_bot_bypassed=False,
            )

        # ── Falha definitiva sem browser ───────────────────────────────────
        if decision.action == CollectionPolicyAction.STOP_FAILURE:
            failure_code = decision.reason or "upstream_error"
            attempts.append(CollectionAttempt(
                layer="http",
                status="failure",
                error_code=failure_code,
                duration_ms=http_ms,
                reason=decision.reason,
            ))
            return CollectedDocument(
                html=None,
                http_status=http_status,
                headers={},
                layer_used="http",
                fallback_taken=False,
                anti_bot_detected=anti_bot_detected,
                anti_bot_pattern=anti_bot_pattern,
                timestamp=ts,
                duration_ms=(time.monotonic() - t_start) * 1000,
                attempts=tuple(attempts),
                error_code=failure_code,
                classification_reason=decision.reason,
                anti_bot_bypassed=False,
            )

        # ── Escalamento para browser ───────────────────────────────────────
        attempts.append(CollectionAttempt(
            layer="http",
            status="escalated",
            error_code=None,
            duration_ms=http_ms,
            reason=decision.reason,
        ))

        html_browser: str | None = None
        browser_error_code: str | None = None
        doc_error_code: str | None = None
        t_browser = time.monotonic()

        try:
            html_browser = await self._browser.fetch(
                url, timeout=browser_to, domain=domain
            )
        except PlaywrightPoolNotReadyError as exc:
            browser_error_code = type(exc).__name__
            doc_error_code = "playwright_not_ready"
            logger.warning("browser_not_ready", url=url)
        except PlaywrightTimeoutError as exc:
            browser_error_code = type(exc).__name__
            doc_error_code = "playwright_timeout"
            logger.warning("browser_timeout", url=url, error=str(exc))
        except PlaywrightFetchError as exc:
            browser_error_code = type(exc).__name__
            doc_error_code = "playwright_fetch_error"
            logger.warning("browser_fetch_error", url=url, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            browser_error_code = type(exc).__name__
            doc_error_code = "browser_fetch_failed"
            logger.warning("browser_fetch_failed", url=url, error=str(exc), error_type=browser_error_code)

        browser_ms = (time.monotonic() - t_browser) * 1000

        residual_pattern: str | None = (
            detect_anti_bot_pattern(html_browser) if html_browser else None
        )
        browser_anti_bot = bool(residual_pattern)
        browser_succeeded = html_browser is not None and not browser_error_code
        anti_bot_bypassed = browser_succeeded and not browser_anti_bot

        attempts.append(CollectionAttempt(
            layer="browser",
            status="success" if browser_succeeded else "failure",
            error_code=browser_error_code,
            duration_ms=browser_ms,
            reason=residual_pattern,
        ))

        return CollectedDocument(
            html=html_browser,
            http_status=http_status,
            headers={},
            layer_used="browser" if html_browser is not None else "http",
            fallback_taken=True,
            anti_bot_detected=anti_bot_detected or browser_anti_bot,
            anti_bot_pattern=anti_bot_pattern or residual_pattern,
            timestamp=ts,
            duration_ms=(time.monotonic() - t_start) * 1000,
            attempts=tuple(attempts),
            error_code=doc_error_code,
            classification_reason=decision.reason,
            anti_bot_bypassed=anti_bot_bypassed,
        )


__all__ = ["CrawleeRuntime"]
