""" Callbacks padronizados para o ciclo de vida de coletas.

``CollectionCallbacks`` centraliza o que acontece após uma coleta terminar —
seja com sucesso ou erro. Toda lógica de reenfileiramento pós-coleta deve
passar por este módulo.

Responsabilidade única:
    Interpretar o resultado de uma coleta, decidir como reenfileirar o
    monitorado e registrar o evento com logs estruturados.

Integração com Celery:
    Os callbacks Celery ``link=`` e ``link_error=`` invocam as tasks
    ``finalize_processing_requeue`` e ``finalize_processing_requeue_error``,
    que por sua vez chamam os métodos deste módulo.

    Por que não usar ``link=`` diretamente para chamar este módulo?
    Porque tasks Celery precisam ser serializáveis e registradas no app.
    ``CollectionCallbacks`` é código Python puro sem overhead de broker.

Fluxo esperado:
    collect_product_task → sucesso → finalize_processing_requeue task
                                   → CollectionCallbacks.on_collection_success()
                                   → CollectionQueue.reenqueue_after_collection()

    collect_product_task → erro    → finalize_processing_requeue_error task
                                   → CollectionCallbacks.on_collection_error()
                                   → CollectionQueue.reenqueue_after_collection() com backoff
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from market_alert.collectors.domain.collection_queue import CollectionQueue
from market_alert.infra.celery.retry_policies import RetryPolicy
from market_alert.collectors.utils.continuous_dispatch import (
    _handle_processing_requeue,
    _should_skip_requeue,
)
from market_alert.products.utils.interval_calculator_products import (
    EVENT_RETRY,
    RetryContext,
    _resolve_next_check_at,
    _utc_now,
    calculate_schedule,
)


logger = logging.getLogger(__name__)

class CollectionCallbacks:
    """ Centraliza callbacks de sucesso e erro para coletas de produtos.

    Todos os métodos são estáticos. Use via ``CollectionCallbacks.on_collection_success()``.
    """

    @staticmethod
    def on_collection_success(
        collect_result: dict,
        monitored_id: str,
        trace_id: str | None = None,
    ) -> None:
        """ Processa resultado de coleta bem-sucedida.

        Delega para ``_handle_processing_requeue`` que já contém a lógica
        consolidada de reenfileiramento com base no ``next_check_at`` persistido.

        Args:
            collect_result: dict retornado por ``collect_product_task`` contendo
                ``outcome``, ``status``, ``reason`` e opcionalmente ``next_retry_at``.
            monitored_id: str UUID do monitorado que foi coletado.
            trace_id: ID de rastreamento distribuído.
        """
        from market_alert.products.utils.interval_calculator_products import _parse_next_retry_at
        from market_alert.collectors.utils.collector_result import _parse_collect_result

        normalized = _parse_collect_result(collect_result)
        next_retry_at = _parse_next_retry_at(normalized.get("next_retry_at"))

        logger.info(
            "collection_callback_success",
            monitored_id=monitored_id,
            outcome=normalized.get("outcome"),
            reason=normalized.get("reason"),
            trace_id=trace_id,
        )

        _handle_processing_requeue(
            monitored_id=monitored_id,
            collect_outcome=normalized.get("outcome"),
            reason=(
                normalized.get("status")
                or normalized.get("reason")
                or normalized.get("outcome")
                or "unknown"
            ),
            trace_id=trace_id,
            next_retry_at=next_retry_at,
        )

    @staticmethod
    def on_collection_error(
        monitored_id: str,
        trace_id: str | None = None,
        reason: str = "collect_task_exception",
    ) -> None:
        """ Processa falha inesperada na task de coleta.

        Reenfileira o monitorado com backoff via ``RetryPolicy`` para garantir
        nova tentativa mesmo quando a task lançou exceção não capturada.

        Args:
            monitored_id: str UUID do monitorado.
            trace_id: ID de rastreamento distribuído.
            reason: motivo da falha (para logs e cálculo de schedule).
        """
        logger.warning(
            "collection_callback_error",
            monitored_id=monitored_id,
            reason=reason,
            trace_id=trace_id,
        )

        _handle_processing_requeue(
            monitored_id=monitored_id,
            collect_outcome=None,
            reason=reason,
            trace_id=trace_id,
        )


__all__ = ["CollectionCallbacks"]
