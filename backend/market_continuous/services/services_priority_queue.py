""" Serviço de fila de prioridade usando Redis Sorted Sets

Este módulo encapsula operações de leitura/escrita necessárias para manter a
fila contínua de coletas. A estrutura é baseada em ``Sorted Sets`` para garantir
ordenação por timestamp com baixa latência e suporte a reordenação dinâmica.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping
from uuid import UUID

from redis import Redis

from shared.utils.redis_client import get_redis_client

from market_alert.core.config_alert import settings


logger = logging.getLogger(__name__)

#Script atômico para evitar concorrência entre workers ao retirar o próximo item
_POP_DUE_SCRIPT = """
local queue_key = KEYS[1]
local processing_key = KEYS[2]
local now = tonumber(ARGV[1])

local items = redis.call('ZRANGEBYSCORE', queue_key, '-inf', now, 'LIMIT', 0, 1)
if #items == 0 then
    return nil
end

local item = items[1]
redis.call('ZREM', queue_key, item)
redis.call('ZADD', processing_key, now, item)
return item
"""

class PriorityQueueService:
    """ Gerencia uma fila de prioridade baseada em Redis Sorted Sets """
    def __init__(
        self,
        client_factory: Callable[[], Redis | None] = get_redis_client,
        *,
        queue_key: str | None = None,
        processing_key: str | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._queue_key = queue_key or settings.PRIORITY_QUEUE_KEY
        self._processing_key = processing_key or settings.PRIORITY_QUEUE_PROCESSING_KEY
        self._metadata_key = f"{self._queue_key}:meta"
        self._pop_script = None

    def _client(self) -> Redis | None:
        """ Obtém cliente Redis com tolerância a falhas de conexão """
        try:
            return self._client_factory()
        except Exception as exc:
            logger.warning("priority_queue_client_error", extra={"error": str(exc)})
            return None

    @staticmethod
    def _to_timestamp(value: datetime | float | int) -> float:
        """ Converte datetime ou número em timestamp com fuso UTC """
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()
        return float(value)

    def enqueue(self, product_id: str, scheduled_at: datetime | float | int) -> bool:
        """ Insere ou atualiza um produto na fila com timestamp informado """
        client = self._client()
        if client is None:
            return False

        score = self._to_timestamp(scheduled_at)
        try:
            client.zadd(self._queue_key, {product_id: score})
            return True
        except Exception as exc:
            logger.warning("priority_queue_enqueue_error", extra={"error": str(exc)})
            return False

    def enqueue_now(self, product_id: str) -> bool:
        """ Insere o produto no topo imediato da fila """
        now = datetime.now(timezone.utc)
        return self.enqueue(product_id, now)

    def enqueue_batch(self, entries: Mapping[str, datetime | float | int]) -> int:
        """ Insere ou atualiza vários produtos em lote na fila """
        client = self._client()
        if client is None:
            return 0

        if not entries:
            return 0

        payload = {
            product_id: self._to_timestamp(timestamp)
            for product_id, timestamp in entries.items()
        }

        try:
            return int(client.zadd(self._queue_key, payload))
        except Exception as exc:
            logger.warning("priority_queue_batch_error", extra={"error": str(exc)})
            return 0

    def update_score(self, product_id: str, scheduled_at: datetime | float | int) -> bool:
        """ Atualiza a pontuação (score) de um produto já enfileirado """
        client = self._client()
        if client is None:
            return False

        score = self._to_timestamp(scheduled_at)
        try:
            client.zadd(self._queue_key, {product_id: score})
            return True
        except Exception as exc:
            logger.warning("priority_queue_update_error", extra={"error": str(exc)})
            return False

    def pop_due(self, now: datetime | float | int | None = None) -> str | None:
        """ Remove e retorna o produto mais urgente cujo score já venceu """
        client = self._client()
        if client is None:
            return None

        current_time = now or datetime.now(timezone.utc)
        timestamp = self._to_timestamp(current_time)

        try:
            if self._pop_script is None:
                self._pop_script = client.register_script(_POP_DUE_SCRIPT)
            result = self._pop_script(
                keys=[self._queue_key, self._processing_key],
                args=[timestamp],
            )
            return str(result) if result else None
        except Exception as exc:
            logger.warning("priority_queue_pop_error", extra={"error": str(exc)})
            return None

    def list_next(self, limit: int = 10) -> list[tuple[str, float]]:
        """ Lista os próximos itens da fila sem removê-los """
        client = self._client()
        if client is None:
            return []

        if limit <= 0:
            return []

        try:
            itms = client.zrange(self._queue_key, 0, max(limit - 1, 0), withscores=True)
            return [(str(item), float(score)) for item, score in itms]
        except Exception as exc:
            logger.warning("priority_queue_list_error", extra={"error": str(exc)})
            return []

    def get_score(self, product_id: str) -> float | None:
        """ Recupera o score atual de um item na fila principal """
        client = self._client()
        if client is None:
            return None

        try:
            score = client.zscore(self._queue_key, product_id)
        except Exception as exc:
            logger.warning("priority_queue_score_error", extra={"error": str(exc)})
            return None

        if score is None:
            return None

        return float(score)

    def remove(self, product_id: str) -> bool:
        """ Remove um produto da fila principal e da fila de processamento """
        client = self._client()
        if client is None:
            return False

        try:
            #Remove de ambos os conjuntos para garantir pausa ou deleção imediata
            client.zrem(self._queue_key, product_id)
            client.zrem(self._processing_key, product_id)
            client.hdel(self._metadata_key, product_id)
            return True
        except Exception as exc:
            logger.warning("priority_queue_remove_error", extra={"error": str(exc)})
            return False

    def size(self) -> int:
        """ Retorna o tamanho atual da fila principal """
        client = self._client()
        if client is None:
            return 0

        try:
            return int(client.zcard(self._queue_key))
        except Exception as exc:
            logger.warning("priority_queue_size_error", extra={"error": str(exc)})
            return 0

    def ready_count(self, now: datetime | float | int | None = None) -> int:
        """ Conta quantos itens já estão prontos para coleta """
        client = self._client()
        if client is None:
            return 0

        current_time = now or datetime.now(timezone.utc)
        timestamp = self._to_timestamp(current_time)

        try:
            return int(client.zcount(self._queue_key, "-inf", timestamp))
        except Exception as exc:
            logger.warning("priority_queue_ready_error", extra={"error": str(exc)})
            return 0

    def drain_processing(self, product_ids: Iterable[str]) -> int:
        """ Remove itens processados do conjunto auxiliar de processamento """
        client = self._client()
        if client is None:
            return 0

        ids = list(product_ids)
        if not ids:
            return 0

        try:
            return int(client.zrem(self._processing_key, *ids))
        except Exception as exc:
            logger.warning("priority_queue_processing_error", extra={"error": str(exc)})
            return 0

    def reclaim_stale_processing(
        self,
        stale_after_seconds: int,
        *,
        now: datetime | float | int | None = None,
    ) -> list[str]:
        """ Recoloca itens parados no processamento de volta à fila principal """
        if stale_after_seconds <= 0:
            return []

        client = self._client()
        if client is None:
            return []

        current_time = now or datetime.now(timezone.utc)
        timestamp = self._to_timestamp(current_time)
        stale_before = timestamp - float(stale_after_seconds)

        try:
            stale_items = client.zrangebyscore(self._processing_key, "-inf", stale_before)
        except Exception as exc:
            logger.warning("priority_queue_processing_stale_error", extra={"error": str(exc)})
            return []

        if not stale_items:
            return []

        decoded_items = [
            item.decode() if isinstance(item, (bytes, bytearray)) else str(item)
            for item in stale_items
        ]

        try:
            #Move os itens de volta para a fila com timestamp atual para nova tentativa
            payload = {item: timestamp for item in decoded_items}
            pipeline = client.pipeline()
            pipeline.zrem(self._processing_key, *decoded_items)
            pipeline.zadd(self._queue_key, payload)
            pipeline.execute()
        except Exception as exc:
            logger.warning("priority_queue_processing_reclaim_error", extra={"error": str(exc)})
            return []

        return decoded_items

    def set_enqueued_at(self, product_id: str, enqueued_at: datetime) -> bool:
        """ Registra o horário de enfileiramento para cálculo de latência """
        client = self._client()
        if client is None:
            return False

        try:
            client.hset(self._metadata_key, product_id, enqueued_at.isoformat())
            return True
        except Exception as exc:
            logger.warning("priority_queue_metadata_error", extra={"error": str(exc)})
            return False

    def get_enqueued_at(self, product_id: str) -> datetime | None:
        """ Recupera o horário de enfileiramento salvo no metadata """
        client = self._client()
        if client is None:
            return None

        try:
            raw_value = client.hget(self._metadata_key, product_id)
        except Exception as exc:
            logger.warning("priority_queue_metadata_error", extra={"error": str(exc)})
            return None

        if not raw_value:
            return None

        try:
            decoded = raw_value.decode() if isinstance(raw_value, (bytes, bytearray)) else str(raw_value)
            return datetime.fromisoformat(decoded)
        except Exception:
            return None

    def is_available(self) -> bool:
        """ Indica se o Redis está disponível para operação imediata """
        return self._client() is not None

def _utc_now() -> datetime:
    """ Retorna horário UTC truncado para facilitar correlação de logs."""
    return datetime.now(timezone.utc).replace(microsecond=0)

def enqueue_monitored_now(
    monitored_id: UUID,
    *,
    source: str,
    queue_service: PriorityQueueService | None = None,
) -> bool:
    """ Enfileira monitorado para execução imediata no coletor contínuo."""
    service = queue_service or PriorityQueueService()
    enqueued_at = _utc_now()
    if not service.enqueue_now(str(monitored_id)):
        logger.warning(
            "priority_queue_enqueue_failed",
            extra={"monitored_id": str(monitored_id), "source": source},
        )
        return False

    service.set_enqueued_at(str(monitored_id), enqueued_at)
    logger.info(
        "priority_queue_enqueued",
        extra={
            "monitored_id": str(monitored_id),
            "source": source,
            "enqueued_at": enqueued_at.isoformat(),
        },
    )
    return True

def enqueue_monitored_at(
    monitored_id: UUID,
    scheduled_at: datetime,
    *,
    source: str,
    queue_service: PriorityQueueService | None = None,
) -> bool:
    """ Enfileira monitorado para execução futura respeitando horário alvo."""
    service = queue_service or PriorityQueueService()
    normalized_time = (
        scheduled_at.replace(tzinfo=timezone.utc)
        if scheduled_at.tzinfo is None
        else scheduled_at
    )

    enqueued_at = _utc_now()
    if not service.enqueue(str(monitored_id), normalized_time):
        logger.warning(
            "priority_queue_schedule_failed",
            extra={
                "monitored_id": str(monitored_id),
                "source": source,
                "scheduled_at": normalized_time.isoformat(),
            },
        )
        return False

    service.set_enqueued_at(str(monitored_id), enqueued_at)
    logger.info(
        "priority_queue_scheduled",
        extra={
            "monitored_id": str(monitored_id),
            "source": source,
            "enqueued_at": enqueued_at.isoformat(),
            "scheduled_at": normalized_time.isoformat(),
        },
    )
    return True

def remove_from_priority_queue(
    product_id: UUID,
    *,
    source: str,
    queue_service: PriorityQueueService | None = None,
) -> bool:
    """ Remove item da fila de prioridade ao pausar ou excluir monitoramento."""
    service = queue_service or PriorityQueueService()
    removed = service.remove(str(product_id))
    if removed:
        logger.info(
            "priority_queue_removed",
            extra={"product_id": str(product_id), "source": source},
        )
    else:
        logger.warning(
            "priority_queue_remove_failed",
            extra={"product_id": str(product_id), "source": source},
        )
    return removed
