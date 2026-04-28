""" Runtime de coleta Crawlee — coordena HttpCollector e PlaywrightBrowserCollector.

CrawleeRuntime orquestra os dois coletores conforme a política de decisão:
    1. HTTP primário via HttpCollector (CurlImpersonateHttpClient + SessionPool do Crawlee)
    2. Política de decisão: ACCEPT / ESCALATE_TO_BROWSER / STOP_UNAVAILABLE / STOP_FAILURE
    3. Fallback para browser via PlaywrightBrowserCollector quando a política indicar
    4. CollectedDocument fechado como fronteira estável entre coleta e orquestração

Lifecycle gerenciado pela aplicação via startup()/shutdown() — registrado em main.py.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from market_scraper.collection.collectors.browser_collector import (
    PlaywrightBrowserCollector,
    PlaywrightFetchError,
    PlaywrightPoolNotReadyError,
    PlaywrightTimeoutError,
)
from market_scraper.collection.collectors.http_collector import HttpCollector
from market_scraper.collection.dto.collected_document import CollectedDocument
from market_scraper.collection.dto.collection_attempt import CollectionAttempt
from market_scraper.collection.policy import CollectionPolicyAction, ResponseClassifierPolicy
from market_scraper.core.config_scraper import settings

if TYPE_CHECKING:
    from market_scraper.collection.collectors.protocols import BrowserCollector

logger = structlog.get_logger("crawlee_runtime")


class CrawleeRuntime:
    """ Runtime Crawlee: HTTP primário (CurlImpersonateHttpClient + SessionPool) com
    fallback automático para browser via política de coleta.

    Stateless após inicialização — pode ser compartilhado entre requisições concorrentes.
    Lifecycle (startup/shutdown) gerenciado pelo lifespan da aplicação FastAPI.
    """

    def __init__(
        self,
        *,
        http_collector: HttpCollector | None = None,
        browser_collector: BrowserCollector | None = None,
        policy: ResponseClassifierPolicy | None = None,
    ) -> None:
        self._http = http_collector or HttpCollector()
        self._browser = browser_collector or PlaywrightBrowserCollector()
        self._policy = policy or ResponseClassifierPolicy()
        self._owns_http = http_collector is None
        self._owns_browser = browser_collector is None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """ Inicializa HttpCollector e PlaywrightBrowserCollector.

        Deve ser chamado no startup da aplicação (lifespan FastAPI).
        """
        if self._owns_http:
            await self._http.startup()

        if self._owns_browser:
            try:
                await self._browser.startup()
            except Exception as exc:
                logger.warning("browser_startup_failed", error=str(exc))

    async def shutdown(self) -> None:
        """ Libera HttpCollector e PlaywrightBrowserCollector.

        Deve ser chamado no shutdown da aplicação (lifespan FastAPI).
        """
        if self._owns_http:
            await self._http.shutdown()

        if self._owns_browser:
            await self._browser.shutdown()

    @property
    def browser_ready(self) -> bool:
        """ True quando o browser Playwright está disponível para fallback."""
        return self._browser.is_ready

    # ── Fetch principal ───────────────────────────────────────────────────────

    async def fetch_with_fallback(
        self,
        url: str,
        *,
        domain: str | None = None,
        http_timeout: float | None = None,
        browser_timeout: float | None = None,
        trace_id: str | None = None,
    ) -> CollectedDocument:
        """ Obtém HTML com fallback automático HTTP → browser conforme política.

        Args:
            url: URL canônica do produto.
            domain: Hostname para reutilização de sessão no browser.
            http_timeout: Orçamento HTTP em segundos (usa config se None).
            browser_timeout: Orçamento browser em segundos (usa config se None).
            trace_id: Identificador de rastreamento para correlação de logs.

        Returns:
            CollectedDocument fechado com HTML (ou None em falha) e telemetria completa.
        """
        bound_logger = logger.bind(trace_id=trace_id) if trace_id else logger
        t_start = time.monotonic()
        ts = time.time()
        http_to = http_timeout if http_timeout is not None else settings.SCRAPER_HTTP_BUDGET_SECONDS
        browser_to = browser_timeout if browser_timeout is not None else settings.SCRAPER_BROWSER_BUDGET_SECONDS
        attempts: list[CollectionAttempt] = []

        # ── Tentativa HTTP primária ───────────────────────────────────────────
        html_http: str | None = None
        http_status: int | None = None
        http_error: Exception | None = None
        http_error_code: str | None = None
        t_http = time.monotonic()

        html_http, http_status, http_error, http_error_code = await self._http.fetch(
            url, timeout=http_to, bound_logger=bound_logger
        )

        http_ms = (time.monotonic() - t_http) * 1000

        #Erros fatais de URL/redirect — sem classificador, sem browser
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
                final_url=url,
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
                final_url=url,
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
                final_url=url,
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
                final_url=url,
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
            bound_logger.warning("browser_not_ready", url=url)
        except PlaywrightTimeoutError as exc:
            browser_error_code = type(exc).__name__
            doc_error_code = "playwright_timeout"
            bound_logger.warning("browser_timeout", url=url, error=str(exc))
        except PlaywrightFetchError as exc:
            browser_error_code = type(exc).__name__
            doc_error_code = "playwright_fetch_error"
            bound_logger.warning("browser_fetch_error", url=url, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            browser_error_code = type(exc).__name__
            doc_error_code = "browser_fetch_failed"
            bound_logger.warning("browser_fetch_failed", url=url, error=str(exc), error_type=browser_error_code)

        browser_ms = (time.monotonic() - t_browser) * 1000

        browser_classification = self._policy.classify_browser_result(html_browser)
        residual_pattern: str | None = browser_classification["anti_bot_pattern"]
        browser_anti_bot: bool = browser_classification["anti_bot_detected"]
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
            final_url=url,
        )

__all__ = ["CrawleeRuntime"]
