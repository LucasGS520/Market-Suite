"""Extração e transformação de dados do pipeline para compor a resposta final.

Responsabilidade única: mapear campos de PipelineOutcome/PipelineContext
para dicionários intermediários usados pelo response_builder.
Sem construção de resposta HTTP — apenas transformação de dados.
"""

from __future__ import annotations

from typing import Any

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.services.synergic_pipeline import PipelineOutcome


def _sanitize_payload(url: str) -> dict[str, str]:
    """Normaliza campos sensíveis antes do registro em log."""
    return {"url": sanitize_log_data(url)}


def _derive_data_quality(context_data: dict[str, Any]) -> str:
    """Deriva indicador de qualidade de aquisição a partir do contexto do pipeline.

    Valores possíveis:
        ``"normal"``            — HTTP direto sem anti-bot.
        ``"degraded_anti_bot"`` — Anti-bot detectado mas dados extraídos (sem Playwright).
        ``"browser_fallback"``  — Playwright acionado (com ou sem anti-bot residual).
    """
    if context_data.get("fallback_taken"):
        return "browser_fallback"
    if context_data.get("anti_bot_detected"):
        return "degraded_anti_bot"
    return "normal"


def _extract_additional_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    """Remove campos padrão preservando apenas metadados adicionais."""
    base_keys = {
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
    }
    extras = {key: value for key, value in data.items() if key not in base_keys and value is not None}
    return extras or None


def _extract_acquisition_payload(context_data: dict[str, Any]) -> dict[str, Any] | None:
    """Expõe telemetria de aquisição de forma aditiva no payload HTTP."""
    acquisition_keys = (
        "layer_used",
        "fallback_taken",
        "classification_reason",
        "http_status",
        "anti_bot_detected",
        "anti_bot_pattern",
        "anti_bot_bypassed",
    )
    if not any(key in context_data for key in acquisition_keys):
        return None

    return {
        "layer_used": context_data.get("layer_used"),
        "fallback_taken": bool(context_data.get("fallback_taken", False)),
        "classification_reason": context_data.get("classification_reason"),
        "http_status": context_data.get("http_status"),
        "anti_bot_detected": bool(context_data.get("anti_bot_detected", False)),
        "anti_bot_pattern": context_data.get("anti_bot_pattern"),
        "anti_bot_bypassed": bool(context_data.get("anti_bot_bypassed", False)),
        "data_quality": _derive_data_quality(context_data),
    }


def _merge_availability_and_status(
    payload: dict[str, Any],
    context_data: dict[str, Any],
) -> dict[str, Any]:
    """Aplica precedência explícita para disponibilidade e último status."""
    merged = dict(payload)
    inferred_availability = context_data.get("availability_inferred")
    if merged.get("availability") is None and inferred_availability is not None:
        merged["availability"] = inferred_availability

    inferred_last_status = context_data.get("last_status_inferred")
    if not merged.get("last_status") and inferred_last_status:
        merged["last_status"] = inferred_last_status

    context_last_status = context_data.get("last_status")
    if not merged.get("last_status") and context_last_status:
        merged["last_status"] = context_last_status

    return merged


def _derive_no_result_reason(outcome: PipelineOutcome) -> str:
    """Deriva motivo explícito quando nenhuma falha de validação foi registrada.

    Distingue quatro causas: HTML indisponível, challenge anti-bot com produto
    (sucesso degradado que parsers não conseguiram converter), domínio sem
    parser dedicado e parsers executados sem dados extraíveis.
    """
    if not outcome.context.html:
        return "html_unavailable"
    if outcome.context.data.get("challenge_residual"):
        return "anti_bot_challenge"
    if outcome.context.data.get("no_domain_parser"):
        return "no_domain_parser"
    return "no_parser_data"


__all__ = [
    "_sanitize_payload",
    "_derive_data_quality",
    "_extract_additional_payload",
    "_extract_acquisition_payload",
    "_merge_availability_and_status",
    "_derive_no_result_reason",
]
