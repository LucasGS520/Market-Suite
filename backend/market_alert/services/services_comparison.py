""" Serviço de comparação e persistência de preços

Carrega o produto monitorado e os seus concorrentes, executa a lógica
de comparação e persiste o resultado obtido
"""

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder
from typing import Tuple, List, Dict, Any, Optional
from decimal import Decimal, InvalidOperation
import structlog
import time

from shared.metrics.metrics_price_comparison import PRICE_COMPARISON_DURATION_SECONDS, PRICE_COMPARISONS_TOTAL, PRICE_ALERTS_TOTAL

from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_comparison import create_price_comparison
from market_alert.models.models_comparisons import PriceComparison
from market_alert.utils.comparator import compare_prices
from market_alert.core.config_alert import settings


logger = structlog.get_logger("comparison_service")

def run_price_comparison(db: Session, monitored_id: UUID, tolerance: Decimal | None = None, price_change_threshold: Decimal | None = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """ Executa a comparação de preços de um produto monitorado, retornando o resultado da comparação e a lista de alertas gerados """
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
        logger.info("comparison_started", monitored_id=str(monitored_id), competitors=len(competitors))

        tol = tolerance if tolerance is not None else Decimal(str(settings.PRICE_TOLERANCE))
        pct = price_change_threshold if price_change_threshold is not None else Decimal(str(settings.PRICE_CHANGE_THRESHOLD))

        #Processa comparação e persiste resultado
        result = compare_prices(monitored, competitors, tol, pct)
        alerts = result.get("alerts", [])
        create_price_comparison(db, monitored.id, jsonable_encoder(result))
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
    
def build_comparison_summary(
    comparison: PriceComparison | None,
    *,
    competitors_count: int,
) -> Dict[str, Any]:
    """ Normaliza campos agregados para consumo do frontend a partir da última comparação """
    summary: Dict[str, Any] = {
        "average_competitor_price": None,
        "min_competitor_price": None,
        "max_competitor_price": None,
        "position_rank": None,
        "competitors_count": competitors_count,
        "last_comparison_at": None,
        "comparison_insights": None,
        "monitored_price": None,
        "discrepancies": [],
        "alerts": [],
    }

    if comparison is None:
        #Sem registros anteriores mantemos valores nulos para evitar falsas leituras
        return summary
    
    data = comparison.data or {}
    summary["last_comparison_at"] = comparison.timestamp
    discrepancies = data.get("discrepancies") or []
    alerts = data.get("alerts") or []
    summary["discrepancies"] = discrepancies
    summary["alerts"] = alerts

    monitored_price = _to_decimal(data.get("monitored_price"))
    average_price = _to_decimal(data.get("average_competitor_price"))
    lowest_block = data.get("lowest_competitor") or {}
    highest_block = data.get("highest_competitor") or {}
    lowest_price = _to_decimal(lowest_block.get("price"))
    highest_price = _to_decimal(highest_block.get("price"))

    if monitored_price is not None:
        summary["monitored_price"] = str(monitored_price)
    if average_price is not None:
        summary["average_competitor_price"] = str(average_price)
    if lowest_price is not None:
        summary["min_competitor_price"] = str(lowest_price)
    if highest_price is not None:
        summary["max_competitor_price"] = str(highest_price)

    competitor_prices = [
        price
        for item in discrepancies
        if (price := _to_decimal(item.get("price"))) is not None
    ]

    if monitored_price is not None and competitor_prices:
        #Rank considera quantos concorrentes possuem preço inferior ao monitorado
        cheaper_count = sum(1 for price in competitor_prices if price < monitored_price)
        summary["position_rank"] = cheaper_count + 1

        if average_price is not None and monitored_price > average_price:
            summary["comparison_insights"] = "Preço monitorado acima da média dos concorrentes."
        elif monitored_price <= min(competitor_prices):
            summary["comparison_insights"] = "Produto monitorado está com melhor preço entre os concorrentes."
        elif monitored_price >= max(competitor_prices):
            summary["comparison_insights"] = "Produto monitorado é o mais caro entre os concorrentes."
        else: 
            summary["comparison_insights"] = "Preço monitorado alinhado com a concorrência."

    return summary
