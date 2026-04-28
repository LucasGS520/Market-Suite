""" ParseProduct canônico — fluxo determinístico sem feature flags.

Sequência fixa e sem ramificações:
    1. robots check (mode=audit: observa; mode=block: rejeita)
    2. rate limiter pre-check (bloqueia domínios em cooldown quando habilitado)
    3. collect  → CrawleeRuntime.fetch_with_fallback → CollectedDocument
    4. extract  → ExtractionChain.run               → ParseResult
    5. post     → PostProcessor.run                 → PostProcessResult
    6. response → build_parser_response             → ParserResponse

A coleta termina antes da extração; nenhuma camada invade responsabilidade da outra.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import perf_counter
from typing import Literal
from uuid import uuid4

import structlog.contextvars
from fastapi import status as http_status
from structlog.stdlib import BoundLogger

from shared.utils.logging_utils import sanitize_log_data
from shared.utils.url_validation import UrlIssue

from market_scraper.collection import CollectedDocument, get_crawlee_runtime
from market_scraper.core.config_scraper import settings
from market_scraper.domain.dtos import AcquisitionTelemetry, ParseResult, PostProcessResult
from market_scraper.extraction import get_extraction_chain
from market_scraper.infra.cache import singleflight
from market_scraper.infra.errors_map import CACHE_INVALIDATING_ERROR_CODES, map_collection_error
from market_scraper.infra.logging.structured_logger import (
    bind_request_context,
    get_scraper_logger,
)
from market_scraper.infra.limits.adaptive_rate_limiter import adaptive_rate_limiter
from market_scraper.post_processing import get_post_processor
from market_scraper.services.telemetry_service import TelemetryService
from market_scraper.services.availability_inference import (
    HTTP_STATUS_UNAVAILABLE,
    infer_availability_from_http_status,
)
from market_scraper.utils.http_utils import extract_domain
from market_scraper.utils.response_builder import build_parser_response
from market_scraper.infra import robots as _robots


logger = get_scraper_logger("parse_product_orchestrator")


# ── Tipos de resultado ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ParseProductSuccess:
    """ Use case concluiu com payload válido para o contrato público."""

    kind: Literal["success"]
    parser_response: object  # shared.schemas.ParserResponse
    stage_timings: dict[str, float]


@dataclass(frozen=True)
class ParseProductNoResult:
    """ Pipeline concluiu mas nenhum parser extraiu dados suficientes."""

    kind: Literal["no_result"]
    reason_code: str | None = None
    stage_timings: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ParseProductError:
    """ Erro de aquisição ou timeout — produz resposta HTTP de erro."""

    kind: Literal["error"]
    issue: UrlIssue
    http_status: int
    stage_timings: dict[str, float]
    invalidate_cache: bool = False


ParseProductResult = ParseProductSuccess | ParseProductNoResult | ParseProductError




# ── Use case ──────────────────────────────────────────────────────────────────

class ParseProduct:
    """ Fluxo determinístico canônico: collect → extract → post_process → response.

    Sem feature flags, sem caminhos legados, sem loops ou retries internos.
    Cada estágio recebe saída tipada do anterior e produz saída tipada própria.
    """

    async def execute(
        self,
        url: str,
        *,
        request_logger: BoundLogger,
        force_refresh: bool = False,
        trace_id: str | None = None,
    ) -> ParseProductResult:
        """ Executa o fluxo completo e retorna resultado tipado por cenário."""
        effective_trace_id = trace_id or str(uuid4())
        structlog.contextvars.bind_contextvars(trace_id=effective_trace_id)

        stage_timings: dict[str, float] = {}
        domain = extract_domain(url) or ""
        request_logger = bind_request_context(
            request_logger,
            trace_id=effective_trace_id,
            domain=domain,
        )
        telemetry = TelemetryService(trace_id=effective_trace_id, domain=domain)
        pipeline_started = perf_counter()

        # ── Estágio 1: collect ────────────────────────────────────────────────
        t = perf_counter()
        telemetry.collection_started(url=url)

        robots_allowed = await _robots.is_allowed(
            url, timeout=settings.SCRAPER_STEP_TIMEOUT_SECONDS
        )
        if not robots_allowed and settings.SCRAPER_ROBOTS_MODE == "block":
            stage_timings["collect"] = perf_counter() - t
            telemetry.collection_completed(
                layer=None,
                duration_ms=int(stage_timings["collect"] * 1000),
            )
            telemetry.pipeline_completed(
                outcome="error",
                total_duration_ms=int((perf_counter() - pipeline_started) * 1000),
                extra={"reason": "robots_disallowed"},
            )
            return ParseProductError(
                kind="error",
                issue=UrlIssue(
                    code="robots_disallowed",
                    message="O acesso à URL foi bloqueado pelas regras de robots.txt",
                ),
                http_status=http_status.HTTP_403_FORBIDDEN,
                stage_timings=stage_timings,
            )

        #Rate limiter pre-check
        allowed, _ = await adaptive_rate_limiter.should_allow(domain)
        if not allowed and settings.SCRAPER_RATE_LIMITER_BLOCK_ENABLED:
            stage_timings["collect"] = perf_counter() - t
            telemetry.collection_completed(
                layer=None,
                duration_ms=int(stage_timings["collect"] * 1000),
            )
            telemetry.pipeline_completed(
                outcome="error",
                total_duration_ms=int((perf_counter() - pipeline_started) * 1000),
                extra={"reason": "rate_limiter_cooldown"},
            )
            request_logger.warning(
                "use_case_rate_limited",
                domain=domain,
                url=sanitize_log_data(url),
            )
            return ParseProductError(
                kind="error",
                issue=UrlIssue(
                    code="rate_limiter_cooldown",
                    message="Limite de requisições atingido para este domínio; tente novamente em instantes",
                ),
                http_status=http_status.HTTP_429_TOO_MANY_REQUESTS,
                stage_timings=stage_timings,
            )

        try:
            singleflight_key = f"{url}|force_refresh={force_refresh}"
            runtime = get_crawlee_runtime()

            async def _fetch() -> CollectedDocument:
                return await runtime.fetch_with_fallback(
                    url,
                    domain=domain,
                    http_timeout=settings.SCRAPER_HTTP_BUDGET_SECONDS,
                    browser_timeout=settings.SCRAPER_BROWSER_BUDGET_SECONDS,
                    trace_id=effective_trace_id,
                )

            doc, _ = await asyncio.wait_for(
                singleflight.coalesce_with_leader(singleflight_key, _fetch),
                timeout=settings.SCRAPER_PIPELINE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            stage_timings["collect"] = perf_counter() - t
            telemetry.collection_completed(
                layer=None,
                duration_ms=int(stage_timings["collect"] * 1000),
            )
            telemetry.pipeline_completed(
                outcome="error",
                total_duration_ms=int((perf_counter() - pipeline_started) * 1000),
                extra={"reason": "pipeline_timeout"},
            )
            request_logger.warning(
                "use_case_stage_timeout",
                stage="collect",
                url=sanitize_log_data(url),
                duration_ms=int(stage_timings["collect"] * 1000),
            )
            return ParseProductError(
                kind="error",
                issue=UrlIssue(
                    code="pipeline_timeout",
                    message="Tempo limite do pipeline excedido",
                ),
                http_status=http_status.HTTP_504_GATEWAY_TIMEOUT,
                stage_timings=stage_timings,
            )

        stage_timings["collect"] = perf_counter() - t
        telemetry.collection_completed(
            layer=doc.layer_used,
            duration_ms=int(stage_timings["collect"] * 1000),
            fallback_taken=doc.fallback_taken,
            anti_bot_detected=doc.anti_bot_detected,
            http_status=doc.http_status,
            classification_reason=doc.classification_reason,
        )

        #Produto definitivamente indisponível (404/410/451) — sem extração
        if (
            not doc.is_successful
            and doc.http_status is not None
            and doc.http_status in HTTP_STATUS_UNAVAILABLE
        ):
            telemetry.pipeline_completed(
                outcome="success",
                total_duration_ms=int((perf_counter() - pipeline_started) * 1000),
                extra={"reason": "product_unavailable", "http_status": doc.http_status},
            )
            return self._build_unavailable_response(
                doc, url, domain, stage_timings, request_logger
            )

        #Erro de coleta — mapeia para resposta de erro HTTP
        if not doc.is_successful:
            issue, status_code = map_collection_error(doc.error_code)
            telemetry.pipeline_completed(
                outcome="error",
                total_duration_ms=int((perf_counter() - pipeline_started) * 1000),
                extra={"reason": issue.code},
            )
            request_logger.info(
                "use_case_stage_blocked",
                stage="collect",
                reason=issue.code,
                url=sanitize_log_data(url),
                duration_ms=int(stage_timings["collect"] * 1000),
            )
            return ParseProductError(
                kind="error",
                issue=issue,
                http_status=status_code,
                stage_timings=stage_timings,
                invalidate_cache=doc.error_code in CACHE_INVALIDATING_ERROR_CODES,
            )

        # ── Estágio 2: extract ────────────────────────────────────────────────
        t = perf_counter()
        telemetry.extraction_started()
        chain = get_extraction_chain()
        parse_result: ParseResult = chain.run(
            doc.html or "",
            url,
            domain,
            http_status=doc.http_status,
        )
        stage_timings["extract"] = perf_counter() - t
        telemetry.extraction_completed(
            parser_used=parse_result.parser_used,
            duration_ms=int(stage_timings["extract"] * 1000),
            succeeded=parse_result.payload is not None,
        )

        request_logger.debug(
            "use_case_extract_done",
            has_payload=parse_result.payload is not None,
            parser_used=parse_result.parser_used,
            url=sanitize_log_data(url),
            duration_ms=int(stage_timings["extract"] * 1000),
        )

        # ── Estágio 3: post_process ───────────────────────────────────────────
        t = perf_counter()
        telemetry.post_processing_started()
        acquisition = AcquisitionTelemetry.from_collected_document(doc)
        processor = get_post_processor()
        post_result: PostProcessResult = processor.run(
            parse_result.payload,
            acquisition,
            url,
            domain,
        )
        stage_timings["post_process"] = perf_counter() - t
        telemetry.post_processing_completed(
            duration_ms=int(stage_timings["post_process"] * 1000),
            is_useful=post_result.is_useful,
            availability=post_result.availability,
        )

        if not post_result.is_useful:
            telemetry.pipeline_completed(
                outcome="no_result",
                total_duration_ms=int((perf_counter() - pipeline_started) * 1000),
                extra={"reason": "extraction_empty"},
            )
            request_logger.info(
                "use_case_stage_no_result",
                stage="post_process",
                url=sanitize_log_data(url),
                duration_ms=int(stage_timings["post_process"] * 1000),
            )
            return ParseProductNoResult(
                kind="no_result",
                reason_code="extraction_empty",
                stage_timings=stage_timings,
            )

        # ── Estágio 4: build_response ─────────────────────────────────────────
        t = perf_counter()
        parser_response = build_parser_response(
            post_result,
            request_logger=request_logger,
        )
        stage_timings["build_response"] = perf_counter() - t

        request_logger.info(
            "use_case_completed",
            url=sanitize_log_data(url),
            duration_collect_ms=int(stage_timings.get("collect", 0) * 1000),
            duration_extract_ms=int(stage_timings.get("extract", 0) * 1000),
            duration_post_process_ms=int(stage_timings.get("post_process", 0) * 1000),
            duration_build_response_ms=int(stage_timings.get("build_response", 0) * 1000),
        )
        telemetry.pipeline_completed(
            outcome="success",
            total_duration_ms=int((perf_counter() - pipeline_started) * 1000),
        )
        return ParseProductSuccess(
            kind="success",
            parser_response=parser_response,
            stage_timings=stage_timings,
        )

    def _build_unavailable_response(
        self,
        doc: CollectedDocument,
        url: str,
        domain: str,
        stage_timings: dict[str, float],
        request_logger: BoundLogger,
    ) -> ParseProductSuccess:
        """ Constrói resposta canônica para produto definitivamente indisponível.

        HTTP 404/410/451: sem extração, disponibilidade inferida do status HTTP.
        """
        stage_timings.setdefault("extract", 0.0)
        stage_timings.setdefault("post_process", 0.0)

        inference = infer_availability_from_http_status(doc.http_status, domain)  # type: ignore[arg-type]

        acquisition = AcquisitionTelemetry(
            layer_used=None,
            fallback_taken=False,
            classification_reason=doc.classification_reason,
            http_status=doc.http_status,
            anti_bot_detected=False,
            anti_bot_pattern=None,
            anti_bot_bypassed=False,
        )
        post_result = PostProcessResult(
            name=None,
            current_price=None,
            currency=None,
            availability=inference.availability,
            last_status=inference.last_status,
            url=url,
            source=domain,
            extra_fields={"acquisition": acquisition.to_payload()},
        )

        t = perf_counter()
        parser_response = build_parser_response(
            post_result,
            request_logger=request_logger,
        )
        stage_timings["build_response"] = perf_counter() - t

        request_logger.info(
            "use_case_product_unavailable",
            url=sanitize_log_data(url),
            http_status=doc.http_status,
            last_status=inference.last_status,
        )
        return ParseProductSuccess(
            kind="success",
            parser_response=parser_response,
            stage_timings=stage_timings,
        )


__all__ = [
    "ParseProductError",
    "ParseProductNoResult",
    "ParseProductResult",
    "ParseProductSuccess",
    "ParseProduct",
]
