""" ParseProductUseCase — orquestração determinística do fluxo de scraping.

Centraliza collect → extract → post_process → build_response em sequência
explícita, eliminando lógica de negócio dispersa na rota HTTP.

A rota HTTP torna-se casca de transporte: validação de entrada, cache
condicional, chamada ao use case e gestão de headers de resposta.

Phase 3 (compatível): cada estágio delega ao pipeline legado (SynergicPipeline).
As fronteiras internas são visíveis nos logs e no timing por estágio.
Phase 4+: cada estágio será substituído por adapter dedicado sem quebra externa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Literal

import structlog
from structlog.stdlib import BoundLogger

from shared.utils.logging_utils import sanitize_log_data
from shared.utils.url_validation import UrlIssue

from market_scraper.routes.error_mapper import _map_http_download_issue
from market_scraper.routes.response_builder import build_success_response, has_useful_payload
from market_scraper.services.pipeline_factory import run_pipeline
from market_scraper.services.synergic_pipeline import PipelineOutcome, PipelineTimeoutError


logger = structlog.get_logger("parse_product_use_case")


# ── Result types ──────────────────────────────────────────────────────────────

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
    outcome: PipelineOutcome
    stage_timings: dict[str, float]


@dataclass(frozen=True)
class ParseProductError:
    """ Erro de aquisição ou timeout — produz resposta HTTP de erro."""

    kind: Literal["error"]
    issue: UrlIssue
    http_status: int
    stage_timings: dict[str, float]
    invalidate_cache: bool = False


ParseProductResult = ParseProductSuccess | ParseProductNoResult | ParseProductError


# ── Use case ─────────────────────────────────────────────────────────────────

class ParseProductUseCase:
    """ Fluxo determinístico collect → extract → post_process → build_response.

    Responsabilidade: coordenar estágios sem fazer I/O de infraestrutura
    diretamente. Redis, browser e HTTP são acessados apenas via portas
    internas (run_pipeline / FetchDecisionGate), nunca pelo use case.
    """

    async def execute(
        self,
        url: str,
        *,
        request_logger: BoundLogger,
        force_refresh: bool = False,
        trace_id: str | None = None,
    ) -> ParseProductResult:
        """ Executa o fluxo completo e retorna um resultado tipado por cenário.

        O caller (rota HTTP) mapeia o resultado para a resposta HTTP correta.
        """
        stage_timings: dict[str, float] = {}

        # ── Estágio 1: collect ────────────────────────────────────────────────
        # Responsabilidade: obter HTML do produto (HTTP primário + browser fallback).
        # Phase 3: delegado ao SynergicPipeline via run_pipeline.
        t = perf_counter()
        try:
            outcome = await run_pipeline(url, force_refresh=force_refresh, trace_id=trace_id)
        except PipelineTimeoutError:
            stage_timings["collect"] = perf_counter() - t
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
                http_status=504,
                stage_timings=stage_timings,
            )
        stage_timings["collect"] = perf_counter() - t

        # ── Estágio 2: extract ────────────────────────────────────────────────
        # Responsabilidade: verificar se a coleta retornou HTML utilizável.
        # Phase 3: a extração real ainda ocorre internamente no pipeline.
        # Este estágio detecta e mapeia falhas de aquisição antes de prosseguir.
        t = perf_counter()
        http_issue_result = _map_http_download_issue(outcome)
        stage_timings["extract"] = perf_counter() - t
        if http_issue_result:
            issue, status_code = http_issue_result
            request_logger.info(
                "use_case_stage_blocked",
                stage="extract",
                reason=issue.code,
                url=sanitize_log_data(url),
                duration_ms=int(stage_timings["extract"] * 1000),
            )
            return ParseProductError(
                kind="error",
                issue=issue,
                http_status=status_code,
                stage_timings=stage_timings,
                invalidate_cache=True,
            )

        # ── Estágio 3: post_process ───────────────────────────────────────────
        # Responsabilidade: validar que o payload extraído satisfaz critério mínimo.
        t = perf_counter()
        is_useful = outcome.status == "success" and has_useful_payload(outcome.payload or {})
        stage_timings["post_process"] = perf_counter() - t
        if not is_useful:
            request_logger.info(
                "use_case_stage_no_result",
                stage="post_process",
                outcome_status=outcome.status,
                url=sanitize_log_data(url),
                duration_ms=int(stage_timings["post_process"] * 1000),
            )
            return ParseProductNoResult(
                kind="no_result",
                outcome=outcome,
                stage_timings=stage_timings,
            )

        # ── Estágio 4: build_response ─────────────────────────────────────────
        # Responsabilidade: normalizar payload para o contrato público ParserResponse.
        t = perf_counter()
        parser_response = build_success_response(
            outcome.payload,
            normalized_url=url,
            outcome=outcome,
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
    "ParseProductUseCase",
]
