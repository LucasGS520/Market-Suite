""" Política de coleção: classifica o resultado de uma tentativa de aquisição.

Define o enum canônico de 4 ações e o adaptador que mapeia o
ResponseClassifier atual para esse contrato. O runtime de coleta e os
adaptadores Crawlee convertem seu resultado para CollectionDecision —
a camada de domínio nunca vê ClassificationAction diretamente.

Mapeamento ClassificationAction → CollectionPolicyAction:
    SUCCESS              → ACCEPT
    SCALE                → ESCALATE_TO_BROWSER
    REJECT (404/410/451) → STOP_UNAVAILABLE   (inferido antes do classificador)
    REJECT (outros)      → STOP_FAILURE
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from market_scraper.services.availability_inference import HTTP_STATUS_UNAVAILABLE
from market_scraper.services.response_classifier import (
    ClassificationAction,
    ResponseClassifier,
    detect_anti_bot_pattern,
)


class CollectionPolicyAction(str, enum.Enum):
    """ Ação canônica decidida pela política de coleção.

    Quatro casos exaustivos — a camada de orquestração ramifica apenas aqui,
    sem precisar conhecer status HTTP ou padrões anti-bot internamente.
    """

    ACCEPT = "accept"
    """ HTML válido obtido — segue para a cadeia de parsing."""

    ESCALATE_TO_BROWSER = "escalate_to_browser"
    """ HTTP não foi suficiente; acionar browser como fallback."""

    STOP_UNAVAILABLE = "stop_unavailable"
    """ Produto definitivamente indisponível (404 / 410 / 451).
    Retornar payload de disponibilidade sem tentar parsing.
    """

    STOP_FAILURE = "stop_failure"
    """ Falha definitiva sem possibilidade de retry útil neste ciclo."""


@dataclass(frozen=True)
class CollectionDecision:
    """ Resultado tipado da política de coleção com telemetria auditável."""

    action: CollectionPolicyAction
    reason: str
    telemetry: dict[str, Any] = field(default_factory=dict)


class ResponseClassifierPolicy:
    """ Adapta ResponseClassifier para o contrato CollectionDecision.

    Consolida a decisão de indisponibilidade (pré-classificador) e a
    decisão de escalonamento (pós-classificador) em um único ponto de
    chamada que devolve CollectionDecision com ação canônica de 4 valores.

    Stateless e thread-safe — pode ser instanciada uma vez e reutilizada.
    """

    def __init__(self, classifier: ResponseClassifier | None = None) -> None:
        self._classifier = classifier or ResponseClassifier()

    def classify(
        self,
        *,
        http_status: int | None,
        html: str | None,
        error: Exception | None,
    ) -> CollectionDecision:
        """ Classifica o resultado de uma tentativa HTTP.

        Args:
            http_status: Código HTTP recebido; ``None`` se houve exceção antes.
            html: HTML obtido; ``None`` em caso de falha.
            error: Exceção capturada; ``None`` em caso de sucesso HTTP.

        Returns:
            CollectionDecision com ação canônica e telemetria.
        """
        #Produto definitivamente indisponível — não vale acionar browser
        if http_status is not None and http_status in HTTP_STATUS_UNAVAILABLE:
            return CollectionDecision(
                action=CollectionPolicyAction.STOP_UNAVAILABLE,
                reason=f"http_{http_status}_unavailable",
                telemetry={"http_status": http_status},
            )

        result = self._classifier.classify(
            http_status=http_status,
            html=html,
            error=error,
        )

        if result.action == ClassificationAction.SUCCESS:
            return CollectionDecision(
                action=CollectionPolicyAction.ACCEPT,
                reason=result.reason,
                telemetry=result.telemetry,
            )

        if result.action == ClassificationAction.SCALE:
            return CollectionDecision(
                action=CollectionPolicyAction.ESCALATE_TO_BROWSER,
                reason=result.reason,
                telemetry=result.telemetry,
            )

        #ClassificationAction.REJECT — tudo mais é falha definitiva
        return CollectionDecision(
            action=CollectionPolicyAction.STOP_FAILURE,
            reason=result.reason,
            telemetry=result.telemetry,
        )

    def classify_browser_result(self, html: str | None) -> dict[str, Any]:
        """ Classifica o HTML obtido via browser para anti-bot residual.

        Centraliza a detecção de padrões anti-bot pós-browser na política,
        mantendo essa decisão fora do runtime de coleta.

        Returns:
            Dict com 'anti_bot_pattern' (str|None) e 'anti_bot_detected' (bool).
        """
        pattern = detect_anti_bot_pattern(html) if html else None
        return {
            "anti_bot_pattern": pattern,
            "anti_bot_detected": bool(pattern),
        }


__all__ = [
    "CollectionDecision",
    "CollectionPolicyAction",
    "ResponseClassifierPolicy",
]
