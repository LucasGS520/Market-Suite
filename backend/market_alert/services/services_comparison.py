""" Serviço de comparação e persistência de preços

O fluxo mantém apenas as etapas essenciais: carregamento de produtos,
execução da comparação e armazenamento do último resumo para consumo do
frontend.
"""

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder
from typing import Tuple, List, Dict, Any, Optional
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import structlog
import time

from shared.metrics.metrics_price_comparison import PRICE_COMPARISON_DURATION_SECONDS, PRICE_COMPARISONS_TOTAL, PRICE_ALERTS_TOTAL

from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_comparison import (
    create_price_comparison,
    upsert_price_comparison_summary,
)
from market_alert.models.models_comparisons import PriceComparison, PriceComparisonSummary
from market_alert.models.models_products import CompetitorProduct
from market_alert.utils.comparator import compare_prices
from market_alert.core.config_alert import settings


logger = structlog.get_logger("comparison_service")

def run_price_comparison(db: Session, monitored_id: UUID, tolerance: Decimal | None = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """ Executa a comparação de preços de um produto monitorado e retorna o resultado calculado """
    start = time.time()
    status = "success"
    result: Dict[str, Any] | None = None
    alerts: List[Dict[str, Any]] = []

    try:
        #Carrega o produto monitorado para validação
        monitored = get_monitored_product_by_id(db, monitored_id)
        if not monitored:
            raise ValueError(f"Monitored product {monitored_id} not found")

        #Recupera concorrentes associados
        competitors = get_competitors_by_monitored_id(db, monitored_id)
        competitors = _deduplicate_competitors(competitors)
        logger.info("comparison_started", monitored_id=str(monitored_id), competitors=len(competitors))

        tol = tolerance if tolerance is not None else Decimal(str(settings.PRICE_TOLERANCE))

        #Processa comparação e persiste resultado
        raw_result = compare_prices(monitored, competitors, tol)
        encoded_result = jsonable_encoder(raw_result)
        alerts = encoded_result.get("alerts", [])

        comparison = create_price_comparison(db, monitored.id, encoded_result)
        summary_payload = _compute_summary_from_payload(
            encoded_result,
            timestamp=comparison.timestamp,
            comparison_id=comparison.id,
            competitors_count=len(competitors),
        )
        encoded_summary = jsonable_encoder(summary_payload)
        upsert_price_comparison_summary(
            db,
            monitored.id,
            comparison.id,
            encoded_summary,
        )
        encoded_result["summary"] = encoded_summary
        encoded_result["comparison_id"] = str(comparison.id)
        encoded_result["monitored_id"] = str(monitored.id)
        encoded_result["user_id"] = str(monitored.user_id)
        result = encoded_result
        logger.info("comparison_finished", monitored_id=str(monitored_id), alerts=len(alerts))

    except Exception:
        status = "failure"
        raise

    finally:
        duration = time.time() - start
        #Registra métricas de duração e status
        PRICE_COMPARISON_DURATION_SECONDS.observe(duration)
        PRICE_COMPARISONS_TOTAL.labels(status=status).inc()
        if result is not None:
            PRICE_ALERTS_TOTAL.inc(len(alerts))

    return result, alerts

def _deduplicate_competitors(competitors: List[CompetitorProduct]) -> List[CompetitorProduct]:
    """Remove duplicidades simples mantendo o concorrente mais recente por ID """

    if not competitors:
        return []

    deduped: dict[str, CompetitorProduct] = {}
    for competitor in competitors:
        reference = str(getattr(competitor, "id", ""))
        if not reference:
            deduped[str(len(deduped))] = competitor
            continue

        existing = deduped.get(reference)
        if existing is None:
            deduped[reference] = competitor
            continue

        existing_checked = getattr(existing, "last_checked", None)
        current_checked = getattr(competitor, "last_checked", None)
        if existing_checked is None or (
            current_checked is not None and current_checked > existing_checked
        ):
            deduped[reference] = competitor

    return list(deduped.values())

def _to_decimal(value: Any) -> Optional[Decimal]:
    """ Converte valores do JSON armazenado para Decimal quando possível """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        #Retorna None quando o valor não pode ser convertido sem perdas
        return None
    
def _empty_summary(competitors_count: int) -> Dict[str, Any]:
    """ Cria estrutura base do resumo competitivo com valores padrão """
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
        "potential_savings": None,
        "comparison_insights": None,
        "discrepancies": [],
        "alerts": [],
    }

def _compute_summary_from_payload(
    payload: Dict[str, Any],
    *,
    timestamp: Any,
    comparison_id: UUID | None,
    competitors_count: int,
) -> Dict[str, Any]:
    """Calcula agregados a partir do payload cru armazenado na comparação """
    summary = _empty_summary(competitors_count)
    summary["last_comparison_at"] = timestamp
    summary["computed_at"] = timestamp
    if comparison_id is not None:
        summary["comparison_id"] = str(comparison_id)

    discrepancies_raw = payload.get("discrepancies") or []
    summary["discrepancies"] = (
        discrepancies_raw if isinstance(discrepancies_raw, list) else []
    )

    alerts_raw = payload.get("alerts") or []
    summary["alerts"] = alerts_raw if isinstance(alerts_raw, list) else []

    monitored_price = _to_decimal(payload.get("monitored_price"))

    if monitored_price is not None:
        summary["monitored_price"] = str(monitored_price)

    competitor_prices: list[Decimal] = []
    for item in summary["discrepancies"]:
        if isinstance(item, dict):
            price = _to_decimal(item.get("price"))
            if price is not None:
                competitor_prices.append(price)

    summary["competitors_with_price_count"] = len(competitor_prices)

    average_price = _to_decimal(payload.get("average_competitor_price"))
    if average_price is None and competitor_prices:
        average_price = (
            sum(competitor_prices) / len(competitor_prices)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    lowest_block = payload.get("lowest_competitor") or {}
    highest_block = payload.get("highest_competitor") or {}
    lowest_price = _to_decimal(lowest_block.get("price"))
    highest_price = _to_decimal(highest_block.get("price"))

    if lowest_price is None and competitor_prices:
        lowest_price = min(competitor_prices)
    if highest_price is None and competitor_prices:
        highest_price = max(competitor_prices)
    if average_price is not None:
        summary["competitors_mean"] = str(average_price)
    if lowest_price is not None:
        summary["competitors_min"] = str(lowest_price)
    if highest_price is not None:
        summary["competitors_max"] = str(highest_price)

    if (
        monitored_price is not None
        and lowest_price is not None
        and monitored_price > lowest_price
    ):
        summary["potential_savings"] = str(
            (monitored_price - lowest_price).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )

    if monitored_price is not None and competitor_prices:
        #Rank considera quantos concorrentes possuem preço inferior ao monitorado
        cheaper_count = sum(1 for price in competitor_prices if price < monitored_price)
        summary["position_rank"] = cheaper_count + 1

        if average_price is not None and monitored_price > average_price:
            summary["comparison_insights"] = "Preço monitorado acima da média dos concorrentes."
        elif lowest_price is not None and monitored_price <= lowest_price:
            summary["comparison_insights"] = "Produto monitorado está com melhor preço entre os concorrentes."
        elif highest_price is not None and monitored_price >= highest_price:
            summary["comparison_insights"] = "Produto monitorado é o mais caro entre os concorrentes."
        else:
            summary["comparison_insights"] = "Preço monitorado alinhado com a concorrência."

    return summary

def _apply_summary_defaults(
    payload: Dict[str, Any],
    *,
    timestamp: Any,
    comparison_id: UUID | None,
    competitors_count: int,
) -> Dict[str, Any]:
    """ Garante que o resumo persistido contenha todos os campos esperados """
    summary = _empty_summary(competitors_count)
    summary.update(payload or {})

    #Preserva o timestamp da última comparação quando já registrado no payload
    if summary.get("last_comparison_at") is None:
        summary["last_comparison_at"] = timestamp
    summary["computed_at"] = timestamp
    summary["competitors_count"] = competitors_count

    if summary.get("discrepancies") is None:
        summary["discrepancies"] = []
    if summary.get("alerts") is None:
        summary["alerts"] = []

    if comparison_id is not None:
        summary["comparison_id"] = summary.get("comparison_id") or str(comparison_id)

    try:
        summary["competitors_with_price_count"] = int(summary["competitors_with_price_count"])
    except (TypeError, ValueError, KeyError):
        summary["competitors_with_price_count"] = 0

    return summary


def build_comparison_summary(
    comparison: PriceComparison | None,
    *,
    competitors_count: int,
    stored_summary: PriceComparisonSummary | None = None,
) -> Dict[str, Any]:
    """ Normaliza os dados de resumo para exposição na API pública """
    if stored_summary is not None:
        return _apply_summary_defaults(
            stored_summary.aggregates or {},
            timestamp=stored_summary.timestamp,
            comparison_id=stored_summary.comparison_id,
            competitors_count=competitors_count,
        )

    if comparison is None:
        return _empty_summary(competitors_count)

    payload = comparison.data or {}
    return _compute_summary_from_payload(
        payload,
        timestamp=comparison.timestamp,
        comparison_id=comparison.id,
        competitors_count=competitors_count,
    )
