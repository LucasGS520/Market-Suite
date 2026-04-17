""" Porta de decisão central para aquisição de HTML em cascata.

Encapsula toda a lógica de decisão de estratégia (HTTP → browser) em um
único ponto testável e sem dependência de ``PipelineContext``.
``FetchHTMLStep`` delega para cá; parsers e demais etapas não conhecem o
mecanismo de aquisição.

Fluxo de decisão::

    Input: url, domain, force_refresh, http_timeout, browser_timeout
        ↓
    [1] Rate limiter pré-check → host bloqueado?
        ├─ SCRAPER_RATE_LIMITER_BLOCK_ENABLED=True  → REJECT imediato (modo produção)
        └─ SCRAPER_RATE_LIMITER_BLOCK_ENABLED=False → observa (log), continua (padrão)
        ↓
    [2] Tentativa HTTP primária — curl_cffi
        ├─ 404/410/451 → REJECT (produto indisponível, sem tentar Playwright)
        ├─ Outro erro HTTP (429, 5xx) → http_exc → Classificador
        └─ Sucesso → html_http → Classificador
        ↓
    [3] ResponseClassifier (avalia UMA tentativa)
        ├─ SUCCESS → FetchResult(status=SUCCESS, layer_used=curl_cffi)
        ├─ REJECT  → FetchResult(status=REJECT)
        └─ SCALE   → tenta Playwright
        ↓
    [4] Fallback de browser — Playwright
        ├─ Sucesso → detecta padrão residual (informativo), anti_bot_bypassed
        │            → FetchResult(status=SUCCESS_AFTER_BROWSER)
        └─ Falha   → FetchResult(status=REJECT_AFTER_BROWSER)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import httpx
import structlog

from market_scraper.core.config_scraper import settings
from market_scraper.infra.adaptive_rate_limiter import adaptive_rate_limiter
from market_scraper.services.availability_inference import (
    HTTP_STATUS_UNAVAILABLE,
    infer_availability_from_http_status,
)
from market_scraper.services.playwright_pool import (
    PlaywrightFetchError,
    PlaywrightPoolNotReadyError,
    PlaywrightTimeoutError,
    playwright_pool,
)
from market_scraper.services.response_classifier import (
    ClassificationAction,
    ResponseClassifier,
    detect_anti_bot_pattern,
)
from market_scraper.utils import singleflight
from market_scraper.utils.http_download import download_html

logger = structlog.get_logger("fetch_decision_gate")

_classifier = ResponseClassifier()


# ─────────────────────────────────────────────────────────────────────────────
# Tipos públicos
# ─────────────────────────────────────────────────────────────────────────────

class FetchStatus(str, enum.Enum):
    """ Status final da tentativa de aquisição de HTML."""
    SUCCESS               = "success"                # curl_cffi retornou HTML válido
    SUCCESS_AFTER_BROWSER = "success_after_browser"  # Playwright retornou HTML válido
    REJECT                = "reject"                 # Rejeição definitiva
    REJECT_AFTER_BROWSER  = "reject_after_browser"   # Playwright também falhou


@dataclass(frozen=True)
class FetchResult:
    """ Resultado completo da aquisição de HTML com telemetria.

    Attributes:
        status: Resultado final da tentativa (ver ``FetchStatus``).
        html: HTML obtido; ``None`` em caso de falha.
        layer_used: ``"curl_cffi"`` ou ``"playwright"``; ``None`` se não chegou a buscar.
        fallback_taken: ``True`` se Playwright foi acionado.
        anti_bot_detected: Padrão anti-bot encontrado em alguma tentativa.
        anti_bot_pattern: Nome do padrão (ex: ``"cloudflare_challenge"``).
        anti_bot_bypassed: ``True`` se Playwright resolveu o challenge sem padrão residual.
        error_code: Código legível para ``StepResult.failure()``.
        http_status: Último código HTTP conhecido.
        classification_reason: Razão da decisão do ``ResponseClassifier``.
        availability: Disponibilidade inferida para produtos indisponíveis (404/410/451).
        last_status: Status textual inferido (ex: ``"unavailable"``).
    """
    status: FetchStatus
    html: str | None = None
    layer_used: str | None = None
    fallback_taken: bool = False
    anti_bot_detected: bool = False
    anti_bot_pattern: str | None = None
    anti_bot_bypassed: bool = False
    error_code: str | None = None
    http_status: int | None = None
    classification_reason: str | None = None
    availability: bool | None = None
    last_status: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Gate principal
# ─────────────────────────────────────────────────────────────────────────────

class FetchDecisionGate:
    """ Decide e executa a estratégia de aquisição de HTML em cascata.

    A classe é stateless — pode ser instanciada uma vez e reutilizada
    concorrentemente. Toda a lógica de decisão (rate limiter, classify,
    fallback Playwright) vive aqui; ``FetchHTMLStep`` delega para cá e
    apenas faz o mapeamento para ``StepResult``.
    """

    async def fetch_with_fallback(
        self,
        url: str,
        *,
        domain: str,
        force_refresh: bool,
        http_timeout: float,
        browser_timeout: float,
    ) -> FetchResult:
        """ Executa a aquisição em cascata e retorna um ``FetchResult`` completo.

        Args:
            url: URL do produto a raspar.
            domain: Hostname extraído (usado pelo rate limiter).
            force_refresh: Quando ``True``, ignora cache (passado ao singleflight key).
            http_timeout: Orçamento em segundos para a tentativa HTTP (curl_cffi).
            browser_timeout: Orçamento em segundos para o fallback Playwright.

        Returns:
            ``FetchResult`` descrevendo o resultado final com telemetria.
        """
        # ── 1. Rate limiter pré-check ─────────────────────────────────────
        allowed, _ = await adaptive_rate_limiter.should_allow(domain)
        if not allowed:
            if settings.SCRAPER_RATE_LIMITER_BLOCK_ENABLED:
                logger.warning(
                    "fetch_gate_blocked_by_rate_limiter",
                    url=url,
                    domain=domain,
                )
                return FetchResult(
                    status=FetchStatus.REJECT,
                    error_code="rate_limiter_cooldown",
                )
            # SCRAPER_RATE_LIMITER_BLOCK_ENABLED=False → apenas observa, não bloqueia
            logger.info(
                "fetch_gate_rate_limiter_cooldown_observed",
                url=url,
                domain=domain,
            )

        # ── 2. Tentativa HTTP primária — curl_cffi ────────────────────────
        layer1_html: str | None = None
        layer1_exc: Exception | None = None
        layer1_status: int | None = None

        async def _download() -> str:
            return await download_html(url, timeout=http_timeout)

        singleflight_key = f"{url}|force_refresh={force_refresh}"
        try:
            layer1_html, is_leader = await singleflight.coalesce_with_leader(
                singleflight_key, _download
            )
            if not is_leader:
                logger.info("fetch_gate_coalesced", url=url, domain=domain)
            layer1_status = 200

        except httpx.TooManyRedirects:
            await adaptive_rate_limiter.update_history(
                domain, success=False, error_code="too_many_redirects"
            )
            return FetchResult(
                status=FetchStatus.REJECT,
                error_code="too_many_redirects",
                http_status=422,
            )

        except (httpx.InvalidURL, httpx.UnsupportedProtocol):
            await adaptive_rate_limiter.update_history(
                domain, success=False, error_code="invalid_url"
            )
            return FetchResult(
                status=FetchStatus.REJECT,
                error_code="invalid_url",
                http_status=422,
            )

        except httpx.HTTPStatusError as exc:
            layer1_status = exc.response.status_code if exc.response is not None else None
            layer1_exc = exc
            if layer1_status is None:
                await adaptive_rate_limiter.update_history(
                    domain, success=False, error_code="unknown"
                )
                raise

            # Produto definitivamente indisponível — não vale acionar Playwright
            if layer1_status in HTTP_STATUS_UNAVAILABLE:
                inference = infer_availability_from_http_status(layer1_status, domain)
                await adaptive_rate_limiter.update_history(
                    domain, success=False, error_code=str(layer1_status), layer_used=1
                )
                return FetchResult(
                    status=FetchStatus.REJECT,
                    error_code="product_unavailable",
                    http_status=layer1_status,
                    availability=inference.availability,
                    last_status=inference.last_status,
                )
            # Outros 4xx/5xx (429, 403, 500, …) — classificador decide escalonamento

        except Exception as exc:
            layer1_exc = exc

        # ── 3. ResponseClassifier ─────────────────────────────────────────
        classification = _classifier.classify(
            http_status=layer1_status,
            html=layer1_html,
            error=layer1_exc,
        )

        if classification.action == ClassificationAction.REJECT:
            await adaptive_rate_limiter.update_history(
                domain,
                success=False,
                error_code=str(layer1_status) if layer1_status else "rejected",
                layer_used=1,
            )
            logger.info(
                "fetch_gate_rejected",
                url=url,
                domain=domain,
                reason=classification.reason,
            )
            if layer1_exc is not None:
                raise layer1_exc
            return FetchResult(
                status=FetchStatus.REJECT,
                error_code=classification.reason,
                http_status=layer1_status,
                classification_reason=classification.reason,
            )

        # Extraído antes dos checks de action para cobrir tanto SUCCESS degradado quanto SCALE
        l1_anti_bot = classification.telemetry.get("anti_bot_pattern")

        if classification.action == ClassificationAction.SUCCESS:
            await adaptive_rate_limiter.update_history(
                domain, success=True, layer_used=1
            )
            logger.info(
                "fetch_gate_layer1_success",
                url=url,
                domain=domain,
                html_size=len(layer1_html),  # type: ignore[arg-type]
                classification_reason=classification.reason,
                anti_bot_pattern=l1_anti_bot,
            )
            return FetchResult(
                status=FetchStatus.SUCCESS,
                html=layer1_html,
                layer_used="curl_cffi",
                fallback_taken=False,
                http_status=200,
                classification_reason=classification.reason,
                anti_bot_detected=l1_anti_bot is not None,
                anti_bot_pattern=l1_anti_bot,
                anti_bot_bypassed=False,
            )

        # ── 4. SCALE → fallback de browser — Playwright ───────────────────
        logger.info(
            "fetch_gate_scale_to_browser",
            url=url,
            domain=domain,
            reason=classification.reason,
            http_status=layer1_status,
            anti_bot_pattern=l1_anti_bot,
        )
        await adaptive_rate_limiter.update_history(
            domain,
            success=False,
            error_code=classification.reason,
            layer_used=1,
        )

        if not playwright_pool.is_ready:
            logger.warning(
                "fetch_gate_playwright_not_ready",
                url=url,
                domain=domain,
                reason=classification.reason,
            )
            error_code = (
                "anti_bot_page"
                if classification.reason == "anti_bot_page"
                else "pipeline_degraded"
            )
            return FetchResult(
                status=FetchStatus.REJECT,
                error_code=error_code,
                anti_bot_detected=l1_anti_bot is not None,
                anti_bot_pattern=l1_anti_bot,
                http_status=layer1_status,
                classification_reason=classification.reason,
            )

        try:
            pw_html = await playwright_pool.fetch_html(url, timeout=browser_timeout)
        except PlaywrightPoolNotReadyError:
            return FetchResult(
                status=FetchStatus.REJECT_AFTER_BROWSER,
                error_code="playwright_not_ready",
                classification_reason=classification.reason,
            )
        except PlaywrightTimeoutError as exc:
            logger.warning(
                "fetch_gate_playwright_timeout",
                url=url,
                domain=domain,
                timeout=exc.timeout,
            )
            await adaptive_rate_limiter.update_history(
                domain, success=False, error_code="timeout", layer_used=3
            )
            return FetchResult(
                status=FetchStatus.REJECT_AFTER_BROWSER,
                error_code="playwright_timeout",
                classification_reason=classification.reason,
            )
        except PlaywrightFetchError as exc:
            logger.warning(
                "fetch_gate_playwright_error",
                url=url,
                domain=domain,
                reason=exc.reason,
            )
            await adaptive_rate_limiter.update_history(
                domain, success=False, error_code="playwright_error", layer_used=3
            )
            return FetchResult(
                status=FetchStatus.REJECT_AFTER_BROWSER,
                error_code="playwright_fetch_error",
                classification_reason=classification.reason,
            )

        # Playwright bem-sucedido — registra sinal anti-bot como informativo,
        # não como barreira. Se padrão residual existir, é telemetria; parsers rodam.
        residual = detect_anti_bot_pattern(pw_html)
        await adaptive_rate_limiter.update_history(domain, success=True, layer_used=3)
        logger.info(
            "fetch_gate_layer3_success",
            url=url,
            domain=domain,
            html_size=len(pw_html),
            l1_reason=classification.reason,
            anti_bot_residual=residual,
        )
        return FetchResult(
            status=FetchStatus.SUCCESS_AFTER_BROWSER,
            html=pw_html,
            layer_used="playwright",
            fallback_taken=True,
            anti_bot_detected=l1_anti_bot is not None or residual is not None,
            anti_bot_pattern=residual or l1_anti_bot,
            anti_bot_bypassed=residual is None,
            http_status=200,
            classification_reason=classification.reason,
        )


fetch_decision_gate = FetchDecisionGate()

__all__ = [
    "FetchDecisionGate",
    "FetchResult",
    "FetchStatus",
    "fetch_decision_gate",
]
