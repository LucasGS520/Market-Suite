""" Calculadora de resumos competitivos de comparação de preços

Responsabilidade: transformar dados brutos de comparação em um resumo
estruturado, com status competitivo, ranking, insights e estatísticas.

Separa do services_comparison.py:
- Funções puras de cálculo (sem I/O)
- Recomposição de resumo a partir do estado atual (usa DB via utils)
- Geração de texto explicativo para o frontend

Regras desta camada:
- Pode importar de: domain, utils, models/enums (read-only), crud via utils
- NÃO importa de: routes, tasks, orchestrator
- Funções puras não acessam banco — recebem dados já carregados
- Funções de rebuild podem acessar banco via services_comparison_utils
"""

from __future__ import annotations

import json
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings
from market_alert.models.models_products import CompetitorProduct
from market_alert.models.models_comparisons import PriceComparison, PriceComparisonSummary
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.comparisons.domain.price_competitiveness import CompetitivenessThresholds, determine_competitiveness_status
from market_alert.products.utils.price_decimal import to_decimal
from market_alert.comparisons.utils.comparison_utils import filter_competitors_for_comparison


logger = structlog.get_logger("comparison_calculator")

__all__ = [
    "empty_summary",
    "coerce_decimal_fields",
    "apply_summary_defaults",
    "compute_summary_from_payload",
    "build_comparison_insights",
    "build_recomputed_summary",
    "summarize_comparison",
    "resolve_monitored_inactive_reason",
    "rebuild_summary_from_current_state",
    "extract_competitors_count",
]

#Limiares de competitividade carregados das configurações no startup
_thresholds = CompetitivenessThresholds.from_config(settings)

def empty_summary(competitors_count: int) -> Dict[str, Any]:
    """ Cria a estrutura base do resumo competitivo com todos os campos em default."""
    return {
        "comparison_id": None,
        "last_comparison_at": None,
        "computed_at": None,
        "monitored_price": None,
        "competitors_count": competitors_count,
        "competitors_with_price_count": 0,
        "competitors_mean": None,
        "competitors_min": None,
        "competitors_max": None,
        "position_rank": None,
        "potential_adjustment": None,
        "ignored_due_to_inactive": False,
        "competitiveness_status": None,
        "comparison_insights": None,
        "discrepancies": [],
        "reason": None,
        "upstream_reason": None,
    }

def coerce_decimal_fields(summary: Dict[str, Any]) -> Dict[str, Any]:
    """ Normaliza campos monetários para Decimal para evitar strings na resposta."""
    monetary_keys = [
        "monitored_price",
        "competitors_mean",
        "competitors_min",
        "competitors_max",
        "potential_adjustment",
    ]
    for key in monetary_keys:
        if key in summary:
            summary[key] = to_decimal(summary.get(key))
    return summary

def _calculate_competitiveness_status(
    monitored_price: Optional[Decimal],
    reference_price: Optional[Decimal],
    thresholds: CompetitivenessThresholds = _thresholds,
) -> Optional[str]:
    """ Define o status competitivo comparando monitorado com o menor concorrente.

    Delega a lógica de classificação para a camada de domínio, usando os
    limiares configurados. Retorna None quando os preços estão ausentes ou
    a referência é inválida (zero ou negativa).

    Args:
        monitored_price: Preço atual do produto monitorado.
        reference_price: Menor preço entre os concorrentes (base de comparação).
        thresholds: Limiares configurados (usa valores de settings por padrão).

    Returns:
        str com valor do CompetitivenessStatus ou None se não calculável.
    """
    if (
        monitored_price is None
        or reference_price is None
        or reference_price <= Decimal("0")
    ):
        return None

    if monitored_price <= reference_price:
        return CompetitivenessStatus.COMPETITIVE.value

    try:
        delta_fraction = (monitored_price - reference_price) / reference_price
    except ZeroDivisionError:
        return None

    if delta_fraction <= Decimal("0"):
        return CompetitivenessStatus.COMPETITIVE.value

    delta_percent = (delta_fraction * Decimal("100")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    return determine_competitiveness_status(delta_percent, thresholds)

def _calculate_percentage_delta(
    monitored_price: Optional[Decimal],
    reference_price: Optional[Decimal],
) -> Optional[Decimal]:
    """ Calcula variação percentual entre o preço monitorado e uma referência.

    Retorna None quando algum valor está ausente ou a referência é zero/negativa.
    """
    if (
        monitored_price is None
        or reference_price is None
        or reference_price <= Decimal("0")
    ):
        return None

    percentage_delta = (
        (monitored_price - reference_price) / reference_price
    ) * Decimal("100")
    return percentage_delta.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def build_comparison_insights(
    *,
    monitored_price: Optional[Decimal],
    competitors_min: Optional[Decimal],
    competitors_count: int,
    position_rank: Optional[int],
    potential_adjustment: Optional[Decimal],
    competitiveness_status: Optional[str],
) -> Optional[str]:
    """ Gera texto explicativo sobre competitividade e ajuste recomendado.

    Casos tratados:
    1. Sem preço do monitorado → mensagem informativa
    2. Dados insuficientes → None
    3. Alinhado ao menor → mensagem de confirmação
    4. Acima do menor → recomendação de redução com valor e percentual

    Returns:
        str com o insight ou None se não houver dados suficientes.
    """
    if monitored_price is None:
        return "Preço do produto monitorado não disponível; recoletores em andamento."
    if competitors_min is None or position_rank is None or competitors_count is None:
        return None

    total_itens = competitors_count + 1 if competitors_count >= 0 else 1
    delta_vs_min = _calculate_percentage_delta(monitored_price, competitors_min)

    if delta_vs_min is None:
        return None

    adjustment_value = potential_adjustment or Decimal("0.00")
    adjustment_pct = None
    if potential_adjustment is not None and monitored_price > Decimal("0"):
        adjustment_pct = (
            (potential_adjustment / monitored_price) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if adjustment_value <= 0:
        return (
            f"Preço alinhado ao menor concorrente (R${competitors_min}). "
            f"Posição atual: #{position_rank} de {total_itens}."
        )

    adjustment_suffix = f" (~{adjustment_pct}%)" if adjustment_pct is not None else ""
    status_hint = (
        f" Status: {competitiveness_status}." if competitiveness_status else ""
    )
    return (
        f"Você está {delta_vs_min}% acima do menor concorrente (R${competitors_min}). "
        f"Posição atual: #{position_rank} de {total_itens}. "
        f"Recomendação: reduzir R${adjustment_value}{adjustment_suffix} para igualar o menor preço."
        f"{status_hint}"
    )

def compute_summary_from_payload(
    payload: Optional[Dict[str, Any]],
    *,
    timestamp: Any,
    comparison_id: Optional[UUID],
    competitors_count: int,
) -> Dict[str, Any]:
    """ Calcula o resumo competitivo a partir do payload cru de uma comparação.

    Cálculos realizados:
    - competitors_mean: média aritmética dos preços (2 casas decimais, ROUND_HALF_UP)
    - competitors_min/max: menor e maior preço
    - position_rank: 1 + quantidade de concorrentes com preço menor que o monitorado
    - potential_adjustment: diferença para o menor concorrente (quando monitorado está acima)
    - competitiveness_status: via _calculate_competitiveness_status()
    - comparison_insights: via build_comparison_insights()

    Args:
        payload: Dicionário com resultado bruto de compare_prices(). Deve conter
            "discrepancies", "monitored_price", "lowest_competitor", etc.
        timestamp: Datetime da comparação para preencher last_comparison_at.
        comparison_id: UUID da comparação associada.
        competitors_count: Total de concorrentes cadastrados (incluindo inativos).

    Returns:
        Dicionário com todos os campos do resumo calculados. Em caso de erro
        de parsing, retorna resumo parcial para evitar perda total de dados.
    """
    summary = empty_summary(competitors_count)
    summary["last_comparison_at"] = timestamp
    summary["computed_at"] = timestamp
    if comparison_id is not None:
        summary["comparison_id"] = str(comparison_id)

    if not isinstance(payload, dict):
        logger.warning(
            "comparison_payload_invalid",
            comparison_id=str(comparison_id) if comparison_id else None,
        )
        return summary

    try:
        discrepancies_raw = payload.get("discrepancies") or []
        summary["discrepancies"] = (
            discrepancies_raw if isinstance(discrepancies_raw, list) else []
        )
        monitored_price = to_decimal(payload.get("monitored_price"))

        summary["ignored_due_to_inactive"] = bool(payload.get("ignored_due_to_inactive"))
        reason = payload.get("reason") or summary.get("reason")
        if reason:
            summary["reason"] = reason

        if monitored_price is not None:
            summary["monitored_price"] = monitored_price

        competitor_prices: list[Decimal] = []

        def _append_price(value: Any) -> None:
            price = to_decimal(value)
            if price is not None and price not in competitor_prices:
                competitor_prices.append(price)

        for item in summary["discrepancies"]:
            if isinstance(item, dict):
                _append_price(item.get("price"))

        lowest_raw = payload.get("lowest_competitor") or {}
        highest_raw = payload.get("highest_competitor") or {}
        _append_price(to_decimal(lowest_raw.get("price")))
        _append_price(to_decimal(highest_raw.get("price")))

        summary["competitors_with_price_count"] = len(competitor_prices)

        if summary["ignored_due_to_inactive"]:
            summary["competitiveness_status"] = None
            summary["comparison_insights"] = None
            return summary

        if competitor_prices:
            competitors_min = min(competitor_prices)
            competitors_max = max(competitor_prices)
            competitors_mean = (
                sum(competitor_prices) / len(competitor_prices)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            summary["competitors_min"] = competitors_min
            summary["competitors_max"] = competitors_max
            summary["competitors_mean"] = competitors_mean

        if (
            monitored_price is not None
            and summary.get("competitors_min") is not None
            and monitored_price > summary.get("competitors_min")
        ):
            summary["potential_adjustment"] = (
                monitored_price - summary.get("competitors_min")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if monitored_price is not None and competitor_prices:
            cheaper_count = sum(1 for p in competitor_prices if p < monitored_price)
            summary["position_rank"] = cheaper_count + 1

        status_reference = summary.get("competitors_min")
        status = _calculate_competitiveness_status(monitored_price, status_reference)
        if status is not None:
            summary["competitiveness_status"] = status

        summary["comparison_insights"] = build_comparison_insights(
            monitored_price=monitored_price,
            competitors_min=summary.get("competitors_min"),
            competitors_count=competitors_count,
            position_rank=summary.get("position_rank"),
            potential_adjustment=summary.get("potential_adjustment"),
            competitiveness_status=summary.get("competitiveness_status"),
        )
        return summary

    except (AttributeError, TypeError, ValueError) as exc:
        price_preview = None
        try:
            price_preview = json.dumps(payload)[:300]
        except Exception:
            price_preview = str(payload)[:300]
        logger.warning(
            "comparison_summary_failed",
            error=str(exc),
            comparison_id=str(comparison_id) if comparison_id else None,
            payload_preview=price_preview,
        )
        return summary

def apply_summary_defaults(
    payload: Dict[str, Any],
    *,
    timestamp: Any,
    comparison_id: Optional[UUID],
    competitors_count: int,
) -> Dict[str, Any]:
    """ Garante que o resumo contenha todos os campos esperados com valores válidos.

    Preenche campos ausentes com defaults, normaliza tipos e recalcula
    competitiveness_status quando ausente. Aplica após compute_summary_from_payload
    para garantir consistência antes de persistir ou retornar ao frontend.
    """
    summary = empty_summary(competitors_count)
    summary.update(payload or {})

    if summary.get("last_comparison_at") is None:
        summary["last_comparison_at"] = timestamp
    summary["computed_at"] = timestamp
    summary["competitors_count"] = competitors_count

    if summary.get("discrepancies") is None:
        summary["discrepancies"] = []

    if comparison_id is not None:
        summary["comparison_id"] = summary.get("comparison_id") or str(comparison_id)

    try:
        summary["competitors_with_price_count"] = int(summary["competitors_with_price_count"])
    except (TypeError, ValueError, KeyError):
        summary["competitors_with_price_count"] = 0

    summary["ignored_due_to_inactive"] = bool(summary.get("ignored_due_to_inactive"))

    if summary["ignored_due_to_inactive"]:
        summary["competitiveness_status"] = None
        summary["comparison_insights"] = None

    summary = coerce_decimal_fields(summary)

    if summary.get("competitiveness_status") is None:
        monitored_price = summary.get("monitored_price")
        status_reference = summary.get("competitors_min")
        status = _calculate_competitiveness_status(monitored_price, status_reference)
        if status is not None:
            summary["competitiveness_status"] = status

    if not summary.get("reason"):
        no_competitors_available = competitors_count == 0 or summary.get(
            "competitors_with_price_count", 0
        ) == 0
        #Não sobrescreve com "sem_concorrentes" quando a ausência é causada por contexto upstream já descrito em upstream_reason
        #O upstream_reason já explica o problema real.
        has_upstream_context = bool(summary.get("upstream_reason"))
        if no_competitors_available and not has_upstream_context:
            summary["reason"] = "sem_concorrentes_disponiveis"

    return summary

def build_recomputed_summary(
    *,
    comparison: Optional[PriceComparison],
    stored_summary: Optional[PriceComparisonSummary],
    competitors_count: int,
) -> Dict[str, Any]:
    """ Recalcula resumo sem usar agregados antigos como base.

    Objetivo: eliminar ambiguidade quando o snapshot está defasado.
    Os valores calculados agora substituem integralmente os agregados antigos.

    Ordem de preferência:
    1. Resumo embutido no payload da comparação (se disponível)
    2. Cálculo a partir do payload bruto da comparação
    3. Normalização do snapshot persistido (fallback sem comparação)
    4. Resumo vazio (sem dados disponíveis)
    """
    if comparison is not None:
        payload = comparison.data or {}
        if isinstance(payload, dict):
            embedded_summary = payload.get("summary")
            if isinstance(embedded_summary, dict):
                return apply_summary_defaults(
                    embedded_summary,
                    timestamp=comparison.timestamp,
                    comparison_id=comparison.id,
                    competitors_count=competitors_count,
                )

        return compute_summary_from_payload(
            payload,
            timestamp=comparison.timestamp,
            comparison_id=comparison.id,
            competitors_count=competitors_count,
        )

    if stored_summary is not None:
        return apply_summary_defaults(
            stored_summary.aggregates or {},
            timestamp=stored_summary.timestamp,
            comparison_id=stored_summary.comparison_id,
            competitors_count=competitors_count,
        )

    summary = empty_summary(competitors_count)
    if competitors_count == 0:
        summary["reason"] = "sem_concorrentes_disponiveis"
    return summary

def summarize_comparison(
    comparison: Optional[PriceComparison],
    stored_summary: Optional[PriceComparisonSummary] = None,
    *,
    force_recompute: bool = False,
) -> Dict[str, Any]:
    """ Normaliza o resumo competitivo em dois modos explícitos.

    Modo padrão (force_recompute=False): normaliza o snapshot persistido
    em stored_summary quando disponível.

    Modo recompute (force_recompute=True): recalcula o resumo a partir do
    estado mais atual conhecido (payload da comparação corrente) sem usar
    stored_summary.aggregates como fonte principal.

    Usado por services_products.build_monitored_response() para construir
    a resposta da lista de produtos monitorados.
    """
    competitors_count = extract_competitors_count(stored_summary)
    if competitors_count == 0 and comparison is not None:
        payload = comparison.data or {}
        if isinstance(payload, dict):
            discrepancies = payload.get("discrepancies")
            if isinstance(discrepancies, list):
                competitors_count = len(discrepancies)

    if force_recompute:
        return build_recomputed_summary(
            comparison=comparison,
            stored_summary=stored_summary,
            competitors_count=competitors_count,
        )

    if stored_summary is not None:
        stored_payload = stored_summary.aggregates or {}
        return apply_summary_defaults(
            stored_payload,
            timestamp=stored_summary.timestamp,
            comparison_id=stored_summary.comparison_id,
            competitors_count=competitors_count,
        )

    if comparison is None:
        summary = empty_summary(competitors_count)
        if competitors_count == 0:
            summary["reason"] = "sem_concorrentes_disponiveis"
        return summary

    payload = comparison.data or {}
    if isinstance(payload, dict):
        embedded_summary = payload.get("summary")
        if isinstance(embedded_summary, dict):
            return apply_summary_defaults(
                embedded_summary,
                timestamp=comparison.timestamp,
                comparison_id=comparison.id,
                competitors_count=competitors_count,
            )

    return compute_summary_from_payload(
        payload,
        timestamp=comparison.timestamp,
        comparison_id=comparison.id,
        competitors_count=competitors_count,
    )

def resolve_monitored_inactive_reason(monitored: Any) -> Optional[str]:
    """ Determina se o monitorado deve ser tratado como inativo na comparação.

    Verifica condições na seguinte ordem:
    1. availability=False → "monitored_unavailable"
    2. last_status em {unavailable, removed, sold_out} → "monitored_unavailable"
    3. status=inactive E sem preço → "monitored_without_price"
    4. sem preço (qualquer status) → "monitored_without_price"

    Returns:
        str com motivo de inatividade, ou None se o monitorado está ativo.
    """
    unavailable_statuses = {"unavailable", "removed", "sold_out"}
    last_status = (getattr(monitored, "last_status", None) or "").lower()
    availability = getattr(monitored, "availability", None)
    has_price = getattr(monitored, "current_price", None) is not None
    monitoring_status = getattr(monitored, "status", None)

    if availability is False:
        return "monitored_unavailable"
    if last_status in unavailable_statuses:
        return "monitored_unavailable"
    if monitoring_status == MonitoredStatus.inactive and not has_price:
        return "monitored_without_price"
    if not has_price:
        return "monitored_without_price"

    return None

def rebuild_summary_from_current_state(
    *,
    db: Session,
    monitored: Any,
    competitors: List[CompetitorProduct],
    stored_summary: Optional[PriceComparisonSummary],
) -> Dict[str, Any]:
    """ Recompõe um resumo competitivo usando o estado atual de monitorado e concorrentes.

    Garante que /monitored e /comparisons/{id}/summary retornem dados consistentes,
    mesmo quando o resumo persistido está desatualizado (ex: novos concorrentes
    cadastrados desde a última comparação).

    Fluxo para monitorado ativo:
    1. Filtra concorrentes elegíveis (via filter_competitors_for_comparison)
    2. Constrói discrepâncias manualmente com preços resolvidos
    3. Preserva motivo do snapshot anterior (se houver)
    4. Calcula e retorna resumo normalizado

    Para monitorado inativo, retorna resumo stub com motivo de inatividade.

    Args:
        db: Sessão ativa para consultas de fallback de preço histórico.
        monitored: Produto monitorado (MonitoredProduct ORM).
        competitors: Lista completa de concorrentes (incluindo pausados/inativos).
        stored_summary: Último resumo persistido (pode ser None).

    Returns:
        Dicionário de resumo pronto para ser comparado com snapshot anterior
        e persistido se houver mudança material.
    """
    competitors_count = len(competitors)
    comparison_id = getattr(stored_summary, "comparison_id", None)
    timestamp = (
        getattr(stored_summary, "timestamp", None)
        if stored_summary is not None
        else None
    ) or datetime.now(timezone.utc)

    stored_payload = (
        stored_summary.aggregates
        if stored_summary is not None and isinstance(stored_summary.aggregates, dict)
        else {}
    )
    stored_reason = stored_payload.get("reason")

    inactive_reason = resolve_monitored_inactive_reason(monitored)
    if inactive_reason:
        payload_stub = {
            "monitored_price": None,
            "discrepancies": [],
            "lowest_competitor": None,
            "highest_competitor": None,
            "reason": inactive_reason,
            "ignored_due_to_inactive": True,
        }
        return apply_summary_defaults(
            compute_summary_from_payload(
                payload_stub,
                timestamp=timestamp,
                comparison_id=comparison_id,
                competitors_count=competitors_count,
            ),
            timestamp=timestamp,
            comparison_id=comparison_id,
            competitors_count=competitors_count,
        )

    monitored_price = to_decimal(getattr(monitored, "current_price", None))
    filtered_competitors = filter_competitors_for_comparison(db, competitors)
    tolerance = Decimal(str(settings.PRICE_TOLERANCE))

    competitor_entries = sorted(
        [(entry.competitor, entry.price) for entry in filtered_competitors.entries],
        key=lambda e: e[1],
    )

    discrepancies: List[Dict[str, Any]] = []
    if competitor_entries:
        min_price = competitor_entries[0][1]
        for competitor, price in competitor_entries:
            pct_below_monitored: Optional[Decimal] = None
            delta_x_monitored: Optional[Decimal] = None
            if monitored_price is not None:
                if monitored_price > Decimal("0") and price < monitored_price:
                    pct_below_monitored = (
                        (monitored_price - price) / monitored_price * Decimal("100")
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                delta_x_monitored = (price - monitored_price).quantize(
                    tolerance,
                    rounding=ROUND_HALF_UP,
                )

            discrepancies.append({
                "competitor_id": str(getattr(competitor, "id", "")),
                "name": getattr(competitor, "name_competitor", "Concorrente"),
                "price": price,
                "pct_below_monitored": pct_below_monitored,
                "delta_x_min_competitor": (price - min_price).quantize(
                    tolerance,
                    rounding=ROUND_HALF_UP,
                ),
                "delta_x_monitored": delta_x_monitored,
            })

    payload = {
        "monitored_price": monitored_price,
        "discrepancies": discrepancies,
        "lowest_competitor": discrepancies[0] if discrepancies else None,
        "highest_competitor": discrepancies[-1] if discrepancies else None,
        "ignored_due_to_inactive": False,
    }
    if stored_reason:
        payload["reason"] = stored_reason

    return apply_summary_defaults(
        compute_summary_from_payload(
            payload,
            timestamp=timestamp,
            comparison_id=comparison_id,
            competitors_count=competitors_count,
        ),
        timestamp=timestamp,
        comparison_id=comparison_id,
        competitors_count=competitors_count,
    )

def extract_competitors_count(
    stored_summary: Optional[PriceComparisonSummary],
) -> int:
    """ Obtém a contagem de concorrentes a partir dos agregados persistidos.

    Lê o campo competitors_count do JSON aggregates. Usa competitors_with_price_count
    como fallback se competitors_count não estiver disponível.

    Args:
        stored_summary: Objeto ORM PriceComparisonSummary ou None.

    Returns:
        int com a contagem de concorrentes, ou 0 se não disponível.
    """
    if stored_summary is None:
        return 0

    aggregates = (
        stored_summary.aggregates
        if isinstance(stored_summary.aggregates, dict)
        else {}
    )
    try:
        raw_count = aggregates.get("competitors_count")
        if raw_count is None:
            raw_count = aggregates.get("competitors_with_price_count", 0)
        return int(raw_count)
    except (TypeError, ValueError):
        return 0
