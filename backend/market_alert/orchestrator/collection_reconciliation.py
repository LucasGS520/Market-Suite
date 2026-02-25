""" Reconciliação da fila de prioridade de coletas.

Garante que todos os monitorados ativos estejam presentes na fila Redis,
corrigindo perdas causadas por reinicializações de worker, falhas de Redis
ou race conditions durante o processamento contínuo.

Responsabilidade única:
    Iterar monitorados ativos, verificar estado na fila e enfileirar os
    ausentes. Não toma decisões de agendamento — usa ``next_check_at``
    do banco como referência.

Quando rodar:
    - Na inicialização do worker de monitoramento.
    - Periodicamente via beat schedule (ex.: a cada hora).
    - Manualmente em situações de emergência pós-deploy.

Por que é seguro rodar em paralelo com o loop contínuo:
    As operações Redis usadas (ZADD com NX/GT) são idempotentes e atômicas.
    O loop contínuo usa POP+ZADD via Lua script atômico. Sobreposição é
    tolerada, mas a flag Redis evita reconciliações simultâneas desnecessárias.

Sincronização:
    Usa flag Redis ``market_alert:collection:reconciliation:running`` com TTL
    para evitar reconciliações simultâneas entre múltiplos workers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from shared.utils.redis_client import get_redis_client

from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import MonitoredProduct
from market_alert.orchestrator.collection_queue import CollectionQueue


logger = logging.getLogger(__name__)

_RECONCILIATION_FLAG_KEY = "market_alert:collection:reconciliation:running"
#TTL da flag: tempo máximo esperado para uma reconciliação completa
_RECONCILIATION_FLAG_TTL_SECONDS = 5 * 60  # 5 minutos

def _utc_now() -> datetime:
    """ Retorna timestamp UTC sem microsegundos """
    return datetime.now(timezone.utc).replace(microsecond=0)

def _normalize_next_check(next_check_at: datetime | None, fallback: datetime) -> datetime:
    """ Normaliza datetime para UTC ou retorna fallback """
    if next_check_at is None:
        return fallback
    if next_check_at.tzinfo is None:
        return next_check_at.replace(tzinfo=timezone.utc)
    return next_check_at.astimezone(timezone.utc)

def _iter_active_monitored(db: Session) -> Iterable[tuple[UUID, datetime | None]]:
    """ Itera monitorados ativos e não pausados para reconciliação """
    return (
        db.query(MonitoredProduct.id, MonitoredProduct.next_check_at)
        .filter(
            MonitoredProduct.paused.is_(False),
            MonitoredProduct.status == MonitoredStatus.active,
        )
        .yield_per(500)
    )

def _acquire_reconciliation_flag() -> bool:
    """ Tenta adquirir a flag de reconciliação em execução.

    Returns:
        True se a flag foi adquirida (reconciliação pode prosseguir).
        False se já há uma reconciliação em andamento.
    """
    client = get_redis_client()
    if client is None:
        #Sem Redis, permite prosseguir para não bloquear a reconciliação
        logger.warning("reconciliation_flag_redis_unavailable")
        return True

    try:
        result = client.set(
            _RECONCILIATION_FLAG_KEY,
            "1",
            ex=_RECONCILIATION_FLAG_TTL_SECONDS,
            nx=True,  # Only set if Not eXists
        )
        return result is not None
    except Exception as exc:
        logger.warning("reconciliation_flag_acquire_error: %s", exc)
        return True  # Permite prosseguir em caso de erro Redis

def _release_reconciliation_flag() -> None:
    """Libera a flag de reconciliação após conclusão."""
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(_RECONCILIATION_FLAG_KEY)
    except Exception as exc:
        logger.warning("reconciliation_flag_release_error: %s", exc)

def reconcile_collection_queue(
    db: Session,
    collection_queue: CollectionQueue | None = None,
) -> dict[str, int]:
    """ Recarrega a fila de prioridade com todos os monitorados ativos.

    Verifica o estado de cada monitorado ativo na fila Redis. Monitorados
    ausentes são enfileirados com o ``next_check_at`` do banco. Monitorados
    em ``processing`` ou já na fila principal são ignorados para evitar
    reenfileiramento indevido durante janelas transitórias de concorrência.

    Usa flag Redis para evitar reconciliações simultâneas. Se já houver uma
    reconciliação em andamento, retorna imediatamente com ``skipped=1``.

    Args:
        db: Sessão ativa injetada pela task chamadora
        collection_queue: instância de ``CollectionQueue`` (cria nova se None).

    Returns:
        dict com estatísticas: ``total``, ``enqueued``, ``failed``, ``skipped``.

    Exemplo::

        stats = reconcile_collection_queue(db)
        print(stats)
        # {"total": 150, "enqueued": 3, "failed": 0, "skipped": 0}
    """
    if not _acquire_reconciliation_flag():
        logger.info("reconciliation_skipped_already_running")
        return {"total": 0, "enqueued": 0, "failed": 0, "skipped": 1}

    queue = collection_queue or CollectionQueue()
    total = 0
    enqueued = 0
    failed = 0
    now = _utc_now()

    try:
        for monitored_id, next_check_at in _iter_active_monitored(db):
            total += 1
            scheduled_at = _normalize_next_check(next_check_at, now)

            status = queue.get_collection_status(monitored_id)
            if status != "not_found":
                logger.debug(
                    "reconciliation_skip_existing_item",
                    extra={
                        "monitored_id": str(monitored_id),
                        "status": status,
                    },
                )
                continue

            if queue.enqueue_for_collection(
                monitored_id,
                scheduled_at,
                source="reconciliation",
            ):
                enqueued += 1
            else:
                failed += 1

        logger.info(
            "reconciliation_complete",
            total=total,
            enqueued=enqueued,
            failed=failed,
        )
    except Exception as exc:
        logger.exception("reconciliation_error: %s", exc)
    finally:
        _release_reconciliation_flag()

    return {"total": total, "enqueued": enqueued, "failed": failed, "skipped": 0}


__all__ = ["reconcile_collection_queue"]
