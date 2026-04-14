""" Compara preços entre produtos monitorados e concorrentes.

O módulo foi simplificado para entregar apenas os indicadores essenciais
utilizados pelos cards do frontend. O foco permanece em identificar o menor e o
maior preço, média dos concorrentes e ranking básico.
"""

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import event
from sqlalchemy.orm import Session

from shared.schemas.shared_schemas_scraper import ScrapeResult
from shared.schemas.collection_catalog import SUCCESSFUL_OUTCOMES
from shared.utils.redis_client import set_key_with_ttl

from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.enums.enums_products import ProductStatus


logger = structlog.get_logger("price_comparator")


def _has_comparison_source_integrity(result: ScrapeResult | None) -> bool:
    """ Exige resultado bem-sucedido e persistido antes de comparar preços. """
    return bool(
        result is not None
        and result.status in SUCCESSFUL_OUTCOMES
        and result.persisted_at is not None
    )

def request_comparison_recompute(monitored_id: UUID, reason: str) -> None:
    """ Despacha ``compare_prices_task`` com debounce Redis para um monitorado.

    Centraliza o disparo de recomputação para manter uma única regra de
    debounce e um único ponto de integração com Celery para comparações.
    """
    debounce_ttl_seconds = int(os.getenv("COMPARE_RECOMPUTE_DEBOUNCE_TTL_SECONDS", "600"))
    debounce_key = f"compare:debounce:{monitored_id}"
    debounce_registered = set_key_with_ttl(
        debounce_key,
        "1",
        debounce_ttl_seconds,
        only_if_absent=True,
    )

    if debounce_registered is False:
        logger.info(
            "compare_recompute_debounced",
            monitored_id=str(monitored_id),
            reason=reason,
            ttl_seconds=debounce_ttl_seconds,
        )
        return

    if debounce_registered is None:
        #Permite continuar sem Redis para não perder consistência de comparação
        logger.warning(
            "compare_recompute_debounce_unavailable",
            monitored_id=str(monitored_id),
            reason=reason,
        )

    from market_alert.infrastructure.celery.domain_task_enqueuer import DomainTaskEnqueuer

    try:
        DomainTaskEnqueuer().enqueue_comparison(monitored_id, reason=reason)
    except Exception:
        logger.exception(
            "compare_recompute_enqueue_failed",
            monitored_id=str(monitored_id),
            reason=reason,
        )

def resolve_recompute_reason(
    *,
    price_changed: bool,
    availability_changed: bool,
    recollection_refreshed: bool,
) -> str | None:
    """Define o motivo principal de recomputação para monitorados e concorrentes.

    A prioridade de precedência mantém consistência nos logs e evita que cada
    CRUD implemente regras próprias para o mesmo cenário.
    """
    if price_changed or availability_changed:
        return "material_change"
    if recollection_refreshed:
        return "recollection_refresh"
    return None

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
    #Defesa-em-profundidade: filter_competitors_for_comparison() já deveria ter feito
    #essa filtragem, mas garantimos aqui caso compare_prices() seja chamado diretamente.
    ignored_statuses = {ProductStatus.unavailable, ProductStatus.removed}
    valid_competitors = [
        c
        for c in competitors
        if c.current_price is not None
        and getattr(c, "status", ProductStatus.available) not in ignored_statuses
        and getattr(c, "availability", None) is not False
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

def dispatch_comparison_for_scrape_result(
    monitored_id: UUID | None,
    result: ScrapeResult | None,
    trace_id: str | None,
    *,
    force: bool = False,
    debounce_ttl_seconds: int = 600,
    countdown_seconds: int = 3,
) -> None:
    """ Agenda comparação apenas quando scraping trouxe alteração relevante """
    if monitored_id is None or result is None:
        return

    #Gating por outcome: comparação só faz sentido quando coleta foi bem-sucedida.
    #Defesa em profundidade além do check de persisted_at — impede comparação
    source_integrity = _has_comparison_source_integrity(result)

    if result.status not in SUCCESSFUL_OUTCOMES:
        logger.debug(
            "compare_dispatch_skipped_non_success_outcome",
            monitored_id=str(monitored_id),
            trace_id=trace_id,
            status=result.status,
            source_integrity=source_integrity,
        )
        return

    if not source_integrity:
        #Evita enfileirar comparação antes do commit terminar de persistir dados
        logger.warning(
            "compare_dispatch_skipped_missing_persisted_at",
            monitored_id=str(monitored_id),
            trace_id=trace_id,
            status=result.status,
            source_integrity=source_integrity,
        )
        return

    changed = bool(getattr(result, "price_changed", False) or getattr(result, "availability_changed", False))
    if not (force or changed):
        return

    reason = "forced_scrape" if force else "material_change"
    request_comparison_recompute(monitored_id, reason)
    logger.info(
        "compare_prices_enqueued",
        monitored_id=str(monitored_id),
        trace_id=trace_id,
        forced=force,
        changed=changed,
        countdown_seconds=countdown_seconds,
        source_integrity=source_integrity,
    )

def schedule_comparison_after_commit(
    session_manager: Session,
    monitored_id: UUID | None,
    result: ScrapeResult | None,
    trace_id: str | None,
    *,
    force: bool,
    debounce_ttl_seconds: int = 600,
    countdown_seconds: int = 3,
) -> None:
    """ Registra callback para disparar comparação após commit da sessão """
    if result is not None and result.persisted_at is not None:
        dispatch_comparison_for_scrape_result(
            monitored_id,
            result,
            trace_id,
            force=force,
            debounce_ttl_seconds=debounce_ttl_seconds,
            countdown_seconds=countdown_seconds,
        )
        return
    
    transaction = session_manager.get_transaction()

    def _dispatch_callback() -> None:
        dispatch_comparison_for_scrape_result(
            monitored_id,
            result,
            trace_id,
            force=force,
            debounce_ttl_seconds=debounce_ttl_seconds,
            countdown_seconds=countdown_seconds,
        )

    if transaction is not None and hasattr(transaction, "on_commit"):
        #Usa hook nativo do SQLAlchemy 2 para garantir execução pós commit
        transaction.on_commit(_dispatch_callback)
        return
    
    if transaction is not None:
        #Fallback registra evento quando o hook on_commit não está disponível
        event.listen(session_manager, "after_commit", lambda _session: _dispatch_callback(), once=True)
        return
    
    #Sem transação ativa, a persistência já ocorreu
    _dispatch_callback()

def _parse_force_compare_(value: str | None) -> bool:
    """ Normaliza a flag de disparo forçado para comparação """
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "calculate_discrepancies",
    "compare_prices",
    "resolve_recompute_reason",
    "request_comparison_recompute",
    "dispatch_comparison_for_scrape_result",
    "schedule_comparison_after_commit",
    "_has_comparison_source_integrity",
    "_parse_force_compare_",
]
