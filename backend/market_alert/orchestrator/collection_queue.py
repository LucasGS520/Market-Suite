""" Abstração de domínio para a fila de prioridade de coletas contínuas.

``CollectionQueue`` encapsula ``PriorityQueueService`` expondo apenas
operações com nomes orientados ao domínio de coleta. Nenhum módulo externo
ao pacote ``orchestrator/`` deve importar ``PriorityQueueService`` diretamente.

Responsabilidade única:
    Gerenciar o ciclo de vida de um monitorado na fila Redis —
    enfileirar, retirar, marcar como processando, reenfileirar e reclamar
    itens travados. Não contém lógica de negócio nem decisões de agendamento.

Fluxo típico de um monitorado:
    enqueue_for_collection()          ← monitorado criado / ativado
         ↓
    pop_next_for_collection()         ← loop contínuo retira o próximo
         ↓
    (coleta em voo — item no processing set)
         ↓
    reenqueue_after_collection()      ← callback de sucesso
    ou mark_as_done()                 ← drena processing sem reenfileirar
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from market_alert.services.services_priority_queue import (
    PriorityQueueService,
    enqueue_monitored_at,
    enqueue_monitored_now,
    remove_from_priority_queue,
)


logger = logging.getLogger(__name__)

class CollectionQueue:
    """Interface de domínio sobre a fila Redis de prioridade.

    Cada método tem semântica clara sobre o estado do monitorado no ciclo
    de coleta contínua. Internamente delega para ``PriorityQueueService``.

    Args:
        _service: instância de PriorityQueueService (injeção para testes).
    """

    def __init__(self, _service: PriorityQueueService | None = None) -> None:
        self._svc = _service or PriorityQueueService()

    # -------------------------------------------------------------------------
    # Operações de domínio
    # -------------------------------------------------------------------------

    def enqueue_for_collection(
        self,
        monitored_id: UUID,
        scheduled_at: datetime,
        *,
        source: str = "collection_queue",
    ) -> bool:
        """ Enfileira monitorado para coleta contínua no horário indicado.

        Args:
            monitored_id: UUID do monitorado.
            scheduled_at: datetime UTC do próximo check desejado.
            source: rótulo para logs (ex.: 'reconciliation', 'lifecycle').

        Returns:
            True se enfileirado com sucesso, False caso contrário.
        """
        return enqueue_monitored_at(
            monitored_id,
            scheduled_at,
            source=source,
            queue_service=self._svc,
        )

    def enqueue_now(
        self,
        monitored_id: UUID,
        *,
        source: str = "collection_queue",
    ) -> bool:
        """ Enfileira monitorado para coleta imediata (prioridade máxima).

        Args:
            monitored_id: UUID do monitorado.
            source: rótulo para logs.

        Returns:
            True se enfileirado com sucesso.
        """
        return enqueue_monitored_now(
            monitored_id,
            source=source,
            queue_service=self._svc,
        )

    def pop_next_for_collection(
        self,
        now: datetime | None = None,
    ) -> str | None:
        """ Remove e retorna o ID do próximo monitorado pronto para coleta.

        Usa Lua script atômico — o item removido da fila principal vai
        diretamente para o ``processing set``.

        Args:
            now: referência de tempo (usa UTC atual se None).

        Returns:
            str com o product_id ou None se não há itens prontos.
        """
        return self._svc.pop_due(now)

    def mark_as_done(self, monitored_ids: Iterable[str]) -> int:
        """ Remove monitorados do conjunto de processamento sem reenfileirar.

        Usado quando o item foi processado (com sucesso ou erro definitivo)
        e o reenfileiramento será feito por outro caminho (ex.: callback).

        Args:
            monitored_ids: IDs a remover do processing set.

        Returns:
            Número de itens efetivamente removidos.
        """
        return self._svc.drain_processing(monitored_ids)

    def reenqueue_after_collection(
        self,
        monitored_id: UUID,
        next_check_at: datetime,
        *,
        source: str = "collection_queue",
    ) -> bool:
        """ Reenfileira monitorado com novo agendamento após coleta concluída.

        Equivalente a ``enqueue_for_collection`` mas semanticamente indica
        que a coleta anterior terminou e o próximo ciclo está sendo agendado.

        Args:
            monitored_id: UUID do monitorado.
            next_check_at: datetime UTC do próximo check calculado.
            source: rótulo para logs.

        Returns:
            True se reenfileirado com sucesso.
        """
        return enqueue_monitored_at(
            monitored_id,
            next_check_at,
            source=source,
            queue_service=self._svc,
        )

    def remove_from_collection(
        self,
        monitored_id: UUID,
        *,
        source: str = "collection_queue",
    ) -> bool:
        """ Remove monitorado da fila — usado ao pausar ou deletar.

        Remove de ambos os sets (fila principal e processing) para garantir
        que o item não seja coletado mesmo que esteja em voo.

        Args:
            monitored_id: UUID do monitorado.
            source: rótulo para logs.

        Returns:
            True se removido com sucesso.
        """
        return remove_from_priority_queue(
            monitored_id,
            source=source,
            queue_service=self._svc,
        )

    def reclaim_stale_items(self, stale_after_seconds: int) -> list[str]:
        """ Recupera itens travados no processing set e os devolve à fila.

        Itens que ficam no processing set por mais de ``stale_after_seconds``
        são considerados travados (worker caiu / task perdida) e retornam
        à fila principal para nova tentativa.

        Args:
            stale_after_seconds: limite de tempo em segundos.

        Returns:
            Lista dos product_ids reclamados.
        """
        return self._svc.reclaim_stale_processing(stale_after_seconds)

    def get_collection_status(self, monitored_id: UUID) -> str:
        """ Retorna o estado atual do monitorado na fila Redis.

        Returns:
            'queued'     — na fila principal aguardando coleta.
            'processing' — no processing set (coleta em andamento).
            'not_found'  — não está em nenhum dos sets.
        """
        product_id = str(monitored_id)
        client = self._svc._client()
        if client is None:
            return "not_found"

        try:
            in_queue = client.zscore(self._svc._queue_key, product_id) is not None
            if in_queue:
                return "queued"
            in_processing = client.zscore(self._svc._processing_key, product_id) is not None
            if in_processing:
                return "processing"
        except Exception as exc:
            logger.warning("collection_queue_status_error: %s", exc)

        return "not_found"

    # -------------------------------------------------------------------------
    # Métricas e diagnóstico (delegam diretamente)
    # -------------------------------------------------------------------------

    def size(self) -> int:
        """ Retorna o tamanho total da fila principal """
        return self._svc.size()

    def ready_count(self, now: datetime | None = None) -> int:
        """ Conta quantos itens estão prontos para coleta no momento """
        return self._svc.ready_count(now)

    def is_available(self) -> bool:
        """ Indica se o Redis está acessível """
        return self._svc.is_available()

    def get_enqueued_at(self, product_id: str) -> datetime | None:
        """ Recupera o horário de enfileiramento do metadata Redis """
        return self._svc.get_enqueued_at(product_id)


__all__ = ["CollectionQueue"]
