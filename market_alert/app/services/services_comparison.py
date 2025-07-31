""" Serviço de comparação e persistência de preços

Carrega o produto monitorado e os seus concorrentes, executa a lógica
de comparação e persiste o resultado obtido
"""

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder
from typing import Tuple, List, Dict, Any
from decimal import Decimal
import structlog
import time

from app.metrics import PRICE_COMPARISON_DURATION_SECONDS, PRICE_COMPARISONS_TOTAL, PRICE_ALERTS_TOTAL

from app.crud.crud_monitored import get_monitored_product_by_id
from app.crud.crud_competitor import get_competitors_by_monitored_id
from app.crud.crud_comparison import create_price_comparison
from app.utils.comparator import compare_prices
from app.core.config import settings


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
