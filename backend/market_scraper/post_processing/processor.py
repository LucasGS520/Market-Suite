""" Pós-processamento unificado de payload extraído.

Centraliza todas as transformações que ocorrem após a extração de dados:
  - Parsing de preço (string → Decimal)
  - Merge e precedência de disponibilidade e last_status
  - Normalização de source/URL
  - Consolidação de telemetria de aquisição em extra_fields["acquisition"]
  - Extração de campos adicionais não-padrão

Aceita dados brutos do ExtractionChain (ParseResult.payload) e telemetria
da camada de coleta (AcquisitionTelemetry), produzindo PostProcessResult
tipado e imutável — pronto para construção da ParserResponse.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.domain.dtos import AcquisitionTelemetry, PostProcessResult
from market_scraper.utils.price import parse_price_str


logger = structlog.get_logger("post_processor")

#Campos base que não migram para extra_fields
_BASE_PAYLOAD_KEYS = frozenset({
    "name",
    "current_price",
    "url",
    "source",
    "marketplace",
    "currency",
    "availability",
    "last_status",
    "etag",
    "not_modified",
})


class PostProcessor:
    """ Pós-processador unificado — transforma payload bruto em PostProcessResult.

    Stateless: pode ser instanciado uma vez e reutilizado em múltiplas requisições.
    """

    def run(
        self,
        payload: dict[str, Any] | None,
        acquisition: AcquisitionTelemetry | None,
        url: str,
        source: str | None,
    ) -> PostProcessResult:
        """ Executa todas as etapas de pós-processamento e retorna resultado tipado.

        Args:
            payload: Payload bruto produzido pela ExtractionChain (None se vazio).
            acquisition: Telemetria de aquisição da camada de coleta (pode ser None).
            url: URL canônica do produto (já normalizada).
            source: Domínio da página (ex.: "mercadolivre.com.br").

        Returns:
            PostProcessResult imutável pronto para montar ParserResponse.
        """
        if not payload:
            return self._empty_result(url, source, acquisition)

        # ── 1. Preço: string → Decimal ────────────────────────────────────────
        current_price = self._parse_price(payload.get("current_price"), url)

        # ── 2. Disponibilidade e last_status — precedência: payload > acquisition ──
        availability = self._resolve_availability(payload, acquisition)
        last_status = self._resolve_last_status(payload)

        # ── 3. Source: payload > argumento externo ────────────────────────────
        resolved_source = (
            payload.get("source")
            or payload.get("marketplace")
            or source
            or ""
        )

        # ── 4. Campos adicionais não-padrão ───────────────────────────────────
        extra_fields = self._extract_extra_fields(payload)

        # ── 5. Telemetria de aquisição consolidada em extra_fields ────────────
        if acquisition is not None:
            extra_fields["acquisition"] = acquisition.to_payload()

        logger.debug(
            "post_processor_result",
            url=sanitize_log_data(url),
            source=resolved_source,
            has_price=current_price is not None,
            availability=availability,
        )

        return PostProcessResult(
            name=payload.get("name") or None,
            current_price=current_price,
            currency=payload.get("currency"),
            availability=availability,
            last_status=last_status,
            url=url,
            source=resolved_source,
            extra_fields=extra_fields,
        )

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _parse_price(self, raw: Any, url: str) -> Decimal | None:
        """Converte valor bruto de preço em Decimal; retorna None em falha."""
        if raw is None:
            return None
        try:
            return parse_price_str(raw, url)
        except (ValueError, Exception):
            logger.warning(
                "post_processor_price_parse_failed",
                raw_price=sanitize_log_data(str(raw)),
                url=sanitize_log_data(url),
            )
            return None

    def _resolve_availability(
        self,
        payload: dict[str, Any],
        acquisition: AcquisitionTelemetry | None,
    ) -> bool | None:
        """Disponibilidade do payload tem precedência sobre status HTTP."""
        availability = payload.get("availability")
        if availability is not None:
            return bool(availability)

        #Fallback: indisponibilidade inferida pelo http_status (via telemetria)
        if acquisition is not None and acquisition.http_status in {404, 410, 451}:
            return False

        return None

    def _resolve_last_status(self, payload: dict[str, Any]) -> str | None:
        """ Retorna last_status do payload quando presente."""
        return payload.get("last_status") or None

    def _extract_extra_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        """ Extrai campos não-padrão do payload para extra_fields."""
        return {
            key: value
            for key, value in payload.items()
            if key not in _BASE_PAYLOAD_KEYS and value is not None
        }

    def _empty_result(
        self,
        url: str,
        source: str | None,
        acquisition: AcquisitionTelemetry | None,
    ) -> PostProcessResult:
        """ Resultado vazio quando extração não produziu payload."""
        extra_fields: dict[str, Any] = {}
        if acquisition is not None:
            extra_fields["acquisition"] = acquisition.to_payload()
        return PostProcessResult(
            name=None,
            current_price=None,
            currency=None,
            availability=None,
            last_status=None,
            url=url,
            source=source or "",
            extra_fields=extra_fields,
        )


__all__ = ["PostProcessor"]
