""" DTOs fechados para as etapas do pipeline de scraping.

Substituem o uso de ``PipelineContext.data`` como dicionário aberto.
Cada DTO representa a saída de uma etapa específica com campos tipados
e imutáveis — facilitando testes unitários e rastreabilidade de telemetria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class AcquisitionTelemetry:
    """ Telemetria obrigatória da etapa de aquisição (HTTP ou browser).

    Substitui os campos avulsos em ``PipelineContext.data`` relativos à camada
    de coleta. Mapeado diretamente para o campo ``acquisition`` de ParserResponse.
    """

    layer_used: str | None
    fallback_taken: bool
    classification_reason: str | None
    http_status: int | None
    anti_bot_detected: bool
    anti_bot_pattern: str | None
    anti_bot_bypassed: bool

    @property
    def data_quality(self) -> str:
        """ Deriva indicador de qualidade: normal, degraded_anti_bot ou browser_fallback."""
        if self.fallback_taken:
            return "browser_fallback"
        if self.anti_bot_detected:
            return "degraded_anti_bot"
        return "normal"

    def to_payload(self) -> dict[str, Any]:
        """ Serializa para o formato esperado em ParserResponse.payload.acquisition."""
        return {
            "layer_used": self.layer_used,
            "fallback_taken": self.fallback_taken,
            "classification_reason": self.classification_reason,
            "http_status": self.http_status,
            "anti_bot_detected": self.anti_bot_detected,
            "anti_bot_pattern": self.anti_bot_pattern,
            "anti_bot_bypassed": self.anti_bot_bypassed,
            "data_quality": self.data_quality,
        }

    @classmethod
    def from_context_data(cls, data: dict[str, Any]) -> AcquisitionTelemetry | None:
        """ Constrói a partir do dict aberto de PipelineContext.data.

        Retorna None quando os campos de aquisição estão ausentes (pipeline
        não executou coleta — ex.: 304 via cache).
        """
        acquisition_keys = (
            "layer_used",
            "fallback_taken",
            "classification_reason",
            "http_status",
            "anti_bot_detected",
            "anti_bot_pattern",
            "anti_bot_bypassed",
        )
        if not any(key in data for key in acquisition_keys):
            return None
        return cls(
            layer_used=data.get("layer_used"),
            fallback_taken=bool(data.get("fallback_taken", False)),
            classification_reason=data.get("classification_reason"),
            http_status=data.get("http_status"),
            anti_bot_detected=bool(data.get("anti_bot_detected", False)),
            anti_bot_pattern=data.get("anti_bot_pattern"),
            anti_bot_bypassed=bool(data.get("anti_bot_bypassed", False)),
        )


@dataclass(frozen=True)
class FetchResult:
    """ Resultado da etapa de aquisição de HTML (HTTP ou browser).

    Representa o output fechado do FetchHTMLStep / FetchDecisionGate.
    html=None indica falha de aquisição (status registrado em error_code).
    """

    html: str | None
    telemetry: AcquisitionTelemetry
    error_code: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.html is not None and self.error_code is None


@dataclass(frozen=True)
class ParseAttempt:
    """ Registro de uma tentativa de parsing por um parser específico."""

    parser_name: str
    step_name: str
    succeeded: bool
    reason_code: str | None = None
    reason_message: str | None = None
    dump_path: str | None = None


@dataclass(frozen=True)
class ParseResult:
    """ Resultado da etapa de parsing em cadeia (extruct → Parsel → BS4).

    payload=None indica que nenhum parser extraiu dados suficientes.
    """

    payload: dict[str, Any] | None
    attempts: tuple[ParseAttempt, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.payload is not None

    @property
    def parser_used(self) -> str | None:
        for attempt in reversed(self.attempts):
            if attempt.succeeded:
                return attempt.parser_name
        return None


@dataclass(frozen=True)
class PostProcessResult:
    """ Resultado da etapa de pós-processamento / normalização.

    Representa o payload pronto para construção da ParserResponse,
    após validação de qualidade e inferência de disponibilidade.
    """

    name: str | None
    current_price: Decimal | None
    currency: str | None
    availability: bool | None
    last_status: str | None
    url: str
    source: str
    extra_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def is_useful(self) -> bool:
        """ Critério canônico: availability=False OU (name + price)."""
        if self.availability is False:
            return True
        return bool(self.name) and self.current_price is not None


__all__ = [
    "AcquisitionTelemetry",
    "FetchResult",
    "ParseAttempt",
    "ParseResult",
    "PostProcessResult",
]
