""" Serviço de fila de prioridade usando Redis Sorted Sets 

Este módulo encapsula operações de leitura/escrita necessárias para manter a
fila contínua de coletas. A estrutura é baseada em ``Sorted Sets`` para garantir
ordenação por timestamp com baixa latência e suporte a reordenação dinâmica. 
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping

from redis import Redis

from market_alert.core.config_alert import settings
from shared.utils.redis_client import get_redis_client


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
        
    def remove(self, product_id: str) -> bool:
        """ Remove um produto da fila principal e da fila de processamento """
        client = self._client()
        if client is None:
            return False
        
        try:
            #Remove de ambos os conjuntos para garantir pausa ou deleção imediata
            client.zrem(self._queue_key, product_id)
            client.zrem(self._processing_key, product_id)
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
        