""" Serviço de telemetria estruturada para o pipeline de scraping.

Define nomes canônicos de eventos e uma interface leve para emiti-los
via structlog, garantindo consistência de campos e rastreabilidade por
trace_id em todas as etapas.

Eventos do pipeline (em ordem de execução):

    collection_started       → início da aquisição HTTP/browser
    collection_completed     → aquisição concluída (sucesso ou fallback)
    extraction_started       → início da cadeia de extração
    extraction_completed     → extração concluída com resultado tipado
    post_processing_started  → início do pós-processamento
    post_processing_completed → pós-processamento concluído
    pipeline_completed       → pipeline inteiro concluído com resposta final

Uso:

    from market_scraper.services.telemetry_service import TelemetryService

    tel = TelemetryService(trace_id="abc-123", domain="example.com")
    tel.collection_started(url=url)
    tel.collection_completed(layer="curl_cffi", duration_ms=120, runtime="custom")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from structlog.stdlib import BoundLogger

from shared.utils.logging_utils import sanitize_log_data
from market_scraper.infra.logging.structured_logger import get_scraper_logger


# ── Nomes canônicos de eventos ────────────────────────────────────────────────

EV_COLLECTION_STARTED = "collection_started"
EV_COLLECTION_COMPLETED = "collection_completed"
EV_EXTRACTION_STARTED = "extraction_started"
EV_EXTRACTION_COMPLETED = "extraction_completed"
EV_POST_PROCESSING_STARTED = "post_processing_started"
EV_POST_PROCESSING_COMPLETED = "post_processing_completed"
EV_PIPELINE_COMPLETED = "pipeline_completed"


@dataclass
class TelemetryService:
    """Emite eventos estruturados do pipeline com contexto de trace_id e domain.

    Não mantém estado de tempo — o caller é responsável por medir duração
    e passar duration_ms. Isso evita acoplamento com event loop e clock.
    """

    trace_id: str
    domain: str
    _logger: BoundLogger = field(init=False)

    def __post_init__(self) -> None:
        self._logger = get_scraper_logger("telemetry").bind(
            trace_id=self.trace_id,
            domain=self.domain,
        )

    # ── Coleta ───────────────────────────────────────────────────────────────

    def collection_started(self, *, url: str) -> None:
        self._logger.info(EV_COLLECTION_STARTED, url=sanitize_log_data(url))

    def collection_completed(
        self,
        *,
        layer: str | None,
        duration_ms: int,
        fallback_taken: bool = False,
        anti_bot_detected: bool = False,
        http_status: int | None = None,
        runtime: str = "crawlee",
        classification_reason: str | None = None,
    ) -> None:
        self._logger.info(
            EV_COLLECTION_COMPLETED,
            layer=layer,
            duration_ms=duration_ms,
            fallback_taken=fallback_taken,
            anti_bot_detected=anti_bot_detected,
            http_status=http_status,
            runtime=runtime,
            classification_reason=classification_reason,
        )

    # ── Extração ─────────────────────────────────────────────────────────────

    def extraction_started(self) -> None:
        self._logger.info(EV_EXTRACTION_STARTED)

    def extraction_completed(
        self,
        *,
        parser_used: str | None,
        duration_ms: int,
        succeeded: bool,
    ) -> None:
        self._logger.info(
            EV_EXTRACTION_COMPLETED,
            parser_used=parser_used,
            duration_ms=duration_ms,
            succeeded=succeeded,
        )

    # ── Pós-processamento ────────────────────────────────────────────────────

    def post_processing_started(self) -> None:
        self._logger.info(EV_POST_PROCESSING_STARTED)

    def post_processing_completed(
        self,
        *,
        duration_ms: int,
        is_useful: bool,
        availability: bool | None,
    ) -> None:
        self._logger.info(
            EV_POST_PROCESSING_COMPLETED,
            duration_ms=duration_ms,
            is_useful=is_useful,
            availability=availability,
        )

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def pipeline_completed(
        self,
        *,
        outcome: str,
        total_duration_ms: int,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._logger.info(
            EV_PIPELINE_COMPLETED,
            outcome=outcome,
            total_duration_ms=total_duration_ms,
            **(extra or {}),
        )


__all__ = [
    "TelemetryService",
    "EV_COLLECTION_STARTED",
    "EV_COLLECTION_COMPLETED",
    "EV_EXTRACTION_STARTED",
    "EV_EXTRACTION_COMPLETED",
    "EV_POST_PROCESSING_STARTED",
    "EV_POST_PROCESSING_COMPLETED",
    "EV_PIPELINE_COMPLETED",
]
