""" Abstração de domínio para a fila de prioridade de coletas contínuas.

``CollectionQueue`` encapsula ``PriorityQueueService`` expondo apenas
operações com nomes orientados ao domínio de coleta. Nenhum módulo externo
ao pacote ``orchestrator/`` deve importar ``PriorityQueueService`` diretamente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from market_continuous.services.services_priority_queue import (
    PriorityQueueService,
    enqueue_monitored_at,
    enqueue_monitored_now,
    remove_from_priority_queue,
)


logger = logging.getLogger(__name__)

class CollectionQueue:
    """ Gerencia o ciclo de vida de um monitorado na fila Redis de coletas. """

    def __init__(self, service: PriorityQueueService | None = None) -> None:
        self._service = service or PriorityQueueService()

    # ------------------------------------------------------------------
    # Leitura de estado
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """ Indica se o Redis está disponível. """
        return self._service.is_available()

    def size(self) -> int:
        """ Tamanho atual da fila principal. """
        return self._service.size()

    def ready_count(self) -> int:
        """ Quantidade de itens prontos para coleta agora. """
        return self._service.ready_count()

    def get_enqueued_at(self, monitored_id: str) -> datetime | None:
        """ Retorna o timestamp de enfileiramento para métricas de latência. """
        return self._service.get_enqueued_at(monitored_id)

    def get_collection_status(self, monitored_id: UUID) -> str:
        """ Retorna o estado do monitorado na fila.

        Returns:
            'queued'     — item na fila principal, aguardando despacho
            'processing' — item no conjunto de processamento (em voo)
            'not_found'  — item ausente em ambas as estruturas
        """
        id_str = str(monitored_id)
        score = self._service.get_score(id_str)
        if score is not None:
            return "queued"

        client = self._service._client()
        if client is None:
            return "not_found"
        try:
            in_processing = client.zscore(self._service._processing_key, id_str)
            if in_processing is not None:
                return "processing"
        except Exception as exc:
            logger.warning("collection_queue_status_error", extra={"error": str(exc)})
        return "not_found"

    # ------------------------------------------------------------------
    # Escrita — enfileiramento
    # ------------------------------------------------------------------

    def enqueue_for_collection(
        self,
        monitored_id: UUID,
        scheduled_at: datetime,
        *,
        source: str,
    ) -> bool:
        """ Enfileira monitorado para coleta na data informada. """
        return enqueue_monitored_at(
            monitored_id,
            scheduled_at,
            source=source,
            queue_service=self._service,
        )

    def enqueue_now(self, monitored_id: UUID, *, source: str) -> bool:
        """ Enfileira monitorado para coleta imediata. """
        return enqueue_monitored_now(
            monitored_id,
            source=source,
            queue_service=self._service,
        )

    def pop_next_for_collection(self) -> str | None:
        """ Remove e retorna o próximo ID de monitorado pronto para coleta. """
        return self._service.pop_due()

    # ------------------------------------------------------------------
    # Escrita — pós-coleta
    # ------------------------------------------------------------------

    def reenqueue_after_collection(
        self,
        monitored_id: UUID,
        next_check_at: datetime,
        *,
        source: str,
    ) -> bool:
        """ Reenfileira monitorado após coleta com horário calculado. """
        return enqueue_monitored_at(
            monitored_id,
            next_check_at,
            source=source,
            queue_service=self._service,
        )

    def mark_as_done(self, monitored_ids: Iterable[str]) -> None:
        """ Remove IDs do conjunto de processamento. """
        self._service.drain_processing(monitored_ids)

    def reclaim_stale_items(self, stale_after_seconds: int) -> list[str]:
        """ Recupera itens parados no processing set para nova tentativa. """
        return self._service.reclaim_stale_processing(stale_after_seconds)

    def remove_from_collection(self, monitored_id: UUID, *, source: str) -> bool:
        """ Remove monitorado completamente da fila (pausa ou deleção). """
        return remove_from_priority_queue(
            monitored_id,
            source=source,
            queue_service=self._service,
        )


__all__ = ["CollectionQueue"]
