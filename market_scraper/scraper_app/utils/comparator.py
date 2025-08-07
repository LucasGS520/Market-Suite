""" Compara preços entre produtos monitorados e concorrentes """

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional

import structlog
from scraper_app.models.models_products import MonitoredProduct, CompetitorProduct
from scraper_app.enums.enums_products import ProductStatus


logger = structlog.get_logger("price_comparator")

def calculate_discrepancies(competitor: CompetitorProduct, monitored_price: Decimal, target_price: Decimal, min_price: Decimal, tolerance: Decimal) -> Dict[str, Any]:
    """ Retorna informações de discrepâncias de um unico concorrente """
    price: Decimal = competitor.current_price

    pct_x_target: Optional[Decimal] = None
    if target_price > 0:
        pct_x_target = (
            (price - target_price) / target_price * 100
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    pct_x_monitored: Optional[Decimal] = None
    if monitored_price > 0:
        pct_x_monitored = (
            (price - monitored_price) / monitored_price * 100
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    delta_x_min = (price - min_price).quantize(tolerance, rounding=ROUND_HALF_UP)

    delta_x_monitored = (price - monitored_price).quantize(
        tolerance, rounding=ROUND_HALF_UP
    )

    old_price = getattr(competitor, "old_price", None)
    change_from_old: Optional[Decimal] = None
    pct_change_from_old: Optional[Decimal] = None
    if old_price is not None:
        change_from_old = (price - old_price).quantize(
            tolerance, rounding=ROUND_HALF_UP
        )
        if old_price != 0:
            pct_change_from_old = (
                change_from_old / old_price * 100
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "competitor_id": str(competitor.id),
        "name": competitor.name_competitor,
        "price": price,
        "pct_x_target": pct_x_target,
        "pct_x_monitored": pct_x_monitored,
        "delta_x_min_competitor": delta_x_min,
        "delta_x_monitored": delta_x_monitored,
        "old_price": old_price,
        "change_from_old": change_from_old,
        "pct_change_from_old": pct_change_from_old
    }

def detect_price_changes(competitor: CompetitorProduct, tolerance: Decimal, change_threshold: Decimal) -> Optional[Dict[str, Any]]:
    """ Detecta mudanças de preço significativas de um produto concorrente """
    old_price = getattr(competitor, "old_price", None)
    if old_price is None:
        return None

    diff_prev = (competitor.current_price - old_price).quantize(
        tolerance, rounding=ROUND_HALF_UP
    )
    pct_change = None
    if old_price != 0:
        pct_change = (
            diff_prev / old_price * 100
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if abs(diff_prev) >= change_threshold:
        alert_type = "price_increase" if diff_prev > 0 else "price_decrease"
        return {
            "competitor_id": str(competitor.id),
            "name": competitor.name_competitor,
            "price": competitor.current_price,
            "old_price": old_price,
            "change": diff_prev,
            "pct_change": pct_change,
            "type": alert_type
        }
    return None

def detect_listing_status(competitor: CompetitorProduct) -> Optional[Dict[str, Any]]:
    """ Retorna um alerta se um concorrente listado for removido ou desabilitado """
    status = getattr(competitor, "status", ProductStatus.available)
    if status == ProductStatus.unavailable:
        return {
            "competitor_id": str(competitor.id),
            "name": competitor.name_competitor,
            "status": "unavailable"
        }
    if status == ProductStatus.removed:
        return {
            "competitor_id": str(competitor.id),
            "name": competitor.name_competitor,
            "status": "removed"
        }
    return None

def compare_prices(monitored: MonitoredProduct, competitors: List[CompetitorProduct], tolerance: Decimal = Decimal("0.01"), price_change_threshold: Optional[Decimal] = None) -> Dict[str, Any]:
    """ Compara preços de um produto monitorado com seus concorrentes """
    #Valor base para referência durante a comparação
    monitored_price = monitored.current_price or Decimal("0")
    target_price = monitored.target_price or Decimal("0")

    #Se não houver concorrentes cadastrados, retorna um resultado vazio
    if not competitors:
        logger.info("no_competitors", monitored_id=str(monitored.id))
        return {
            "monitored_price": monitored_price,
            "target_price": target_price,
            "average_competitor_price": None,
            "lowest_competitor": None,
            "highest_competitor": None,
            "discrepancies": [],
            "alerts": []
        }

    #Filtra concorrentes que possuem preço válido
    valid_competitors = [c for c in competitors if c.current_price is not None]

    #Se nenhum concorrente possui preço válido, retorna resultado vazio
    if not valid_competitors:
        logger.info("no_competitor_prices", monitored_id=str(monitored.id))
        return {
            "monitored_price": monitored_price,
            "target_price": target_price,
            "average_competitor_price": None,
            "lowest_competitor": None,
            "highest_competitor": None,
            "discrepancies": [],
            "alerts": []
        }

    #Extrai lista de preços válidos dos concorrentes
    prices = [c.current_price for c in valid_competitors]
    min_price = min(prices)
    max_price = max(prices)
    avg_price = (sum(prices) / len(prices)).quantize(tolerance, rounding=ROUND_HALF_UP)

    #Identifica os concorrentes com menor e maior preço
    lowest = min(valid_competitors, key=lambda c: c.current_price)
    highest = max(valid_competitors, key=lambda c: c.current_price)

    #Monta lista de discrepâncias e possíveis alertas
    discrepancies: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []

    change_threshold = price_change_threshold or tolerance

    for c in valid_competitors:
        price: Decimal = c.current_price

        diff_x_monitored = None
        if monitored_price is not None:
            diff_x_monitored = (
                (price - monitored_price).quantize(tolerance, rounding=ROUND_HALF_UP))

        logger.debug("price_diff", monitored_id=str(monitored.id), competitor_id=str(c.id), base_price=str(monitored_price), competitor_price=str(price), diff=str(diff_x_monitored))

        discrepancies.append(
            calculate_discrepancies( c, monitored_price, target_price, min_price, tolerance)
        )

        status_alert = detect_listing_status(c)
        if status_alert:
            alerts.append(status_alert)

        price_change_alert = detect_price_changes(c, tolerance, change_threshold)
        if price_change_alert:
            alerts.append(price_change_alert)

        #Gera alertas para quem está abaixo do preço-alvo
        if target_price > 0 and price < (target_price - tolerance):
            pct_below = (
                (target_price - price) / target_price * 100
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            alerts.append({
                "competitor_id": str(c.id),
                "name": c.name_competitor,
                "price": price,
                "pct_below_target": pct_below
            })

    monitored_status = getattr(monitored, "status", ProductStatus.available)
    if monitored_status == ProductStatus.unavailable:
        alerts.append({
            "product_id": str(monitored.id),
            "status": "unavailable"
        })
    elif monitored_status == ProductStatus.removed:
        alerts.append({
            "product_id": str(monitored.id),
            "status": "removed"
        })

    result = {
        "monitored_price": monitored_price,
        "target_price": target_price,
        "average_competitor_price": avg_price,
        "lowest_competitor": calculate_discrepancies(
            lowest, monitored_price, target_price, min_price, tolerance
        ),
        "highest_competitor": calculate_discrepancies(
            highest, monitored_price, target_price, min_price, tolerance
        ),
        "discrepancies": discrepancies,
        "alerts": alerts
    }

    logger.info("comparison_summary", monitored_id=str(monitored.id), base_price=str(monitored_price), lowest_price=str(lowest.current_price), highest_price=str(highest.current_price))

    logger.debug("comparison_result", lowest=str(lowest.id), highest=str(highest.id))
    return result
