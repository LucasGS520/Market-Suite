""" Triggers pós-coleta para operações que dependem do resultado.

Este módulo encapsula decisões de "o que fazer após uma coleta" que são
responsabilidade de domínios diferentes da própria coleta. O exemplo
principal é o disparo de comparação de preços.

Responsabilidade única:
    Ler o resultado de uma coleta e decidir se dispara ações em outros
    domínios (comparação, notificação). Não contém lógica de scraping,
    fila Redis nem retry.

Comentário de arquitetura:
    Comparação é responsabilidade separada, disparada após coleta bem-sucedida.
    ``collector_product_task`` não deve conhecer detalhes de comparação —
    apenas chama ``trigger_comparison_if_needed()`` e segue em frente.

Uso em ``collect_product()``::

    from market_alert.colectors.domain.collection_triggers import trigger_comparison_if_needed

    triggered = trigger_comparison_if_needed(
        monitored_id=monitored_id,
        payload=payload,
        collect_result=result,
    )
"""

from __future__ import annotations

import logging
from uuid import UUID

from backend.shared.schemas.shared_schemas_scraper import ScrapeResult

from market_alert.schemas.schemas_collection_payload import CollectionPayload
from market_alert.comparisons.utils.price_comparator import (
    _parse_force_compare_,
    dispatch_comparison_for_scrape_result,
)


logger = logging.getLogger(__name__)

def trigger_comparison_if_needed(
    monitored_id: UUID | None,
    payload: CollectionPayload | dict | None,
    collect_result: ScrapeResult | None,
) -> bool:
    """ Dispara comparação de preços se o resultado da coleta justificar.

    Verifica três condições antes de enfileirar a comparação:
    1. ``monitored_id`` e ``collect_result`` devem ser não-nulos.
    2. O resultado deve ter ``persisted_at`` preenchido (dados persistidos no DB).
    3. Houve mudança de preço/disponibilidade OU ``force_compare=True`` no payload.

    Enfileira via ``dispatch_comparison_for_scrape_result()`` que aplica
    debounce Redis para evitar comparações duplicadas por produto.

    Args:
        monitored_id: UUID do monitorado. Se None, retorna False imediatamente.
        payload: ``CollectionPayload`` tipado ou dict legado com ``force_compare``.
        collect_result: ``ScrapeResult`` retornado pelo scraper.

    Returns:
        True se comparação foi enfileirada, False caso contrário.

    Exemplo::

        triggered = trigger_comparison_if_needed(
            monitored_id=monitored_id,
            payload=payload,
            collect_result=result,
        )
        if triggered:
            logger.info("comparison_triggered", monitored_id=str(monitored_id))
    """
    if monitored_id is None or collect_result is None:
        return False

    #Extrai flag force_compare do payload (suporta CollectionPayload e dict legado)
    force_compare_raw: str | None = None
    if isinstance(payload, CollectionPayload):
        force_compare_raw = payload.force_compare
    elif isinstance(payload, dict):
        force_compare_raw = payload.get("force_compare")

    force = _parse_force_compare_(force_compare_raw)

    #Só enfileira se houve mudança relevante ou flag de força
    changed = bool(
        getattr(collect_result, "price_changed", False)
        or getattr(collect_result, "availability_changed", False)
    )
    if not (force or changed):
        return False

    if collect_result.persisted_at is None:
        logger.debug(
            "trigger_comparison_skipped_no_persist",
            monitored_id=str(monitored_id),
            force=force,
        )
        return False

    dispatch_comparison_for_scrape_result(
        monitored_id,
        collect_result,
        trace_id=None,
        force=force,
    )
    logger.debug(
        "trigger_comparison_dispatched",
        monitored_id=str(monitored_id),
        force=force,
        changed=changed,
    )
    return True


__all__ = ["trigger_comparison_if_needed"]
