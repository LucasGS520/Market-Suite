""" Compara preços entre produtos monitorados e concorrentes.

O módulo foi simplificado para entregar apenas os indicadores essenciais
utilizados pelos cards do frontend. O foco permanece em identificar o menor e o
maior preço, média dos concorrentes e ranking básico.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional

import structlog
from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.enums.enums_products import ProductStatus


logger = structlog.get_logger("price_comparator")

def calculate_discrepancies(
    competitor: CompetitorProduct,
    monitored_price: Decimal | None,
    min_price: Decimal,
    tolerance: Decimal,
) -> Dict[str, Any]:
    """ Calcula discrepâncias básicas para um concorrente.

    Mantém somente deltas essenciais para exibir no dashboard, evitando
    metadados históricos e variações complexas. Quando o preço monitorado
    está ausente, os deltas relacionados ao monitorado permanecem nulos para
    evitar conclusões indevidas de competitividade.
    """
    price: Decimal = competitor.current_price

    pct_below_monitored: Optional[Decimal] = None
    delta_x_monitored: Optional[Decimal] = None
    if monitored_price is not None:
        if monitored_price > 0 and price < monitored_price:
            pct_below_monitored = (
                (monitored_price - price) / monitored_price * 100
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        delta_x_monitored = (price - monitored_price).quantize(
            tolerance, rounding=ROUND_HALF_UP
        )

    delta_x_min = (price - min_price).quantize(tolerance, rounding=ROUND_HALF_UP)

    return {
        "competitor_id": str(competitor.id),
        "name": competitor.name_competitor,
        "price": price,
        "pct_below_monitored": pct_below_monitored,
        "delta_x_min_competitor": delta_x_min,
        "delta_x_monitored": delta_x_monitored,
    }

def compare_prices(
    monitored: MonitoredProduct,
    competitors: List[CompetitorProduct],
    tolerance: Decimal = Decimal("0.01"),
) -> Dict[str, Any]:
    """ Compara preços de um produto monitorado com seus concorrentes
    
    Estrutura de retorno:
    - monitored_price: preço atual do produto monitorado
    - average_competitor_price: média dos preços válidos dos concorrentes ou `None`
    - lowest_competitor/highest_competitor: discrepâncias completas do menor e do maior preço
    - discrepancies: discrepâncias de todos os concorrentes com preço válido
    """
    #Valor base para referência durante a comparação
    monitored_price = monitored.current_price

    #Se não houver concorrentes cadastrados, retorna um resultado vazio
    if not competitors:
        logger.info("no_competitors", monitored_id=str(monitored.id))
        return {
            "monitored_price": monitored_price,
            "average_competitor_price": None,
            "lowest_competitor": None,
            "highest_competitor": None,
            "discrepancies": [],
        }

    #Filtra concorrentes disponíveis com preço válido
    ignored_statuses = {ProductStatus.unavailable, ProductStatus.removed}
    valid_competitors = [
        c
        for c in competitors
        if c.current_price is not None
        and getattr(c, "status", ProductStatus.available) not in ignored_statuses
    ]

    #Se nenhum concorrente possui preço válido, retorna resultado vazio
    if not valid_competitors:
        logger.info("no_competitor_prices", monitored_id=str(monitored.id))
        return {
            "monitored_price": monitored_price,
            "average_competitor_price": None,
            "lowest_competitor": None,
            "highest_competitor": None,
            "discrepancies": [],
        }

    #Extrai lista de preços válidos dos concorrentes
    prices = [c.current_price for c in valid_competitors]
    min_price = min(prices)
    max_price = max(prices)
    avg_price = (sum(prices) / len(prices)).quantize(tolerance, rounding=ROUND_HALF_UP)

    #Identifica os concorrentes com menor e maior preço
    lowest = min(valid_competitors, key=lambda c: c.current_price)
    highest = max(valid_competitors, key=lambda c: c.current_price)

    #Monta lista de discrepâncias
    discrepancies: List[Dict[str, Any]] = []

    for c in valid_competitors:
        price: Decimal = c.current_price

        diff_x_monitored = None
        if monitored_price is not None:
            diff_x_monitored = (
                (price - monitored_price).quantize(tolerance, rounding=ROUND_HALF_UP))

        logger.debug("price_diff", monitored_id=str(monitored.id), competitor_id=str(c.id), base_price=str(monitored_price), competitor_price=str(price), diff=str(diff_x_monitored))

        discrepancy = calculate_discrepancies(
            c, monitored_price, min_price, tolerance
        )
        discrepancies.append(discrepancy)

    result = {
        "monitored_price": monitored_price,
        "average_competitor_price": avg_price,
        "lowest_competitor": calculate_discrepancies(
            lowest, monitored_price, min_price, tolerance
        ),
        "highest_competitor": calculate_discrepancies(
            highest, monitored_price, min_price, tolerance
        ),
        "discrepancies": discrepancies,
    }

    logger.info("comparison_summary", monitored_id=str(monitored.id), base_price=str(monitored_price), lowest_price=str(lowest.current_price), highest_price=str(highest.current_price))

    logger.debug("comparison_result", lowest=str(lowest.id), highest=str(highest.id))
    return result
