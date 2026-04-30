""" DTOs fechados para as etapas do pipeline de scraping.

Substituem o compartilhamento de dicionários abertos entre camadas.
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

    Substitui campos avulsos de telemetria da camada de coleta. Mapeado
    diretamente para o campo ``acquisition`` de ParserResponse.
    """

    layer_used: str | None
    fallback_taken: bool
    classification_reason: str | None
    http_status: int | None
    anti_bot_detected: bool
    anti_bot_pattern: str | None
    anti_bot_bypassed: bool
    is_degraded: bool = False

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
            "is_degraded": self.is_degraded,
        }

    @classmethod
    def from_collected_document(cls, doc: Any) -> "AcquisitionTelemetry":
        """Constrói a partir de um CollectedDocument (camada de coleta canônica)."""
        return cls(
            layer_used=doc.layer_used,
            fallback_taken=doc.fallback_taken,
            classification_reason=doc.classification_reason,
            http_status=doc.http_status,
            anti_bot_detected=doc.anti_bot_detected,
            anti_bot_pattern=doc.anti_bot_pattern,
            anti_bot_bypassed=doc.anti_bot_bypassed,
            is_degraded=getattr(doc, "is_degraded", False),
        )


@dataclass(frozen=True)
class ParseAttempt:
    """ Registro de uma tentativa de parsing por um parser específico."""

    parser_name: str
    step_name: str
    succeeded: bool
    reason_code: str | None = None
    reason_message: str | None = None
    dump_path: str | None = None
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ParseResult:
    """ Resultado da etapa de parsing em cadeia (extruct → Parsel → BS4).

    payload=None indica que nenhum parser extraiu dados suficientes.
    duration_ms registra o tempo total da cadeia completa de extração.
    """

    payload: dict[str, Any] | None
    attempts: tuple[ParseAttempt, ...] = field(default_factory=tuple)
    duration_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.payload is not None

    @property
    def is_successful(self) -> bool:
        """Alias canônico de ``succeeded`` alinhado ao spec da camada de extração."""
        return self.payload is not None

    @property
    def parser_used(self) -> str | None:
        for attempt in reversed(self.attempts):
            if attempt.succeeded:
                return attempt.parser_name
        return None

    @property
    def first_successful_parser(self) -> str | None:
        """Alias canônico de ``parser_used`` alinhado ao spec da camada de extração."""
        return self.parser_used


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
    "ParseAttempt",
    "ParseResult",
    "PostProcessResult",
]
