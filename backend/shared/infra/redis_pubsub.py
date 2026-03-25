""" Utilidades para publicar e propagar eventos via Redis Pub/Sub.

Fornece helpers simplificados para publicar mensagens em canais Redis e
um assinante baseado em threads que repassa os eventos para filas
assíncronas. O módulo é usado pelos serviços para distribuir eventos e
atualizações em tempo real sem bloquear a aplicação principal.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import redis
import structlog

from shared.core.config_base import ConfigBase
from shared.utils.redis_client import get_redis_operational


logger = structlog.get_logger("redis.pubsub")
_settings = ConfigBase()

def publish_message(channel: str, payload: dict[str, Any]) -> bool:
    """ Publica ``payload`` no canal informado usando Redis Pub/Sub.

    A função converte o dicionário para JSON antes de publicar e ignora
    erros de conexão retornando ``False`` quando o Redis estiver
    indisponível. O retorno ``True`` indica que a mensagem foi enviada ao
    menos para um cliente Redis, cabendo ao assinante entregar ao
    consumidor final.
    """

    client = get_redis_operational()
    if client is None:
        logger.warning("redis_pubsub_publish_skipped", channel=channel, reason="client_unavailable")
        return False

    try:
        message = json.dumps(payload)
        client.publish(channel, message)
        logger.debug("redis_pubsub_published", channel=channel)
        return True
    except Exception as exc:  # pragma: no cover - falha inesperada de cliente
        logger.error("redis_pubsub_publish_failed", channel=channel, error=str(exc))
        return False

class RedisChannelSubscriber:
    """ Mantém assinatura contínua em um canal Redis e repassa eventos.

    A implementação utiliza uma *thread* dedicada para consumir o
    ``PubSub`` do Redis e enviar os eventos para uma fila ``asyncio``
    thread-safe. O consumidor pode aguardar os eventos chamando
    :meth:`get`, normalmente a partir de uma *coroutine* executando no
    *event loop* principal da aplicação FastAPI.
    """

    def __init__(self, channel: str, *, reconnect_interval: float = 2.0) -> None:
        self.channel = channel
        self.reconnect_interval = reconnect_interval
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def queue(self) -> asyncio.Queue[dict[str, Any]]:
        """ Retorna a fila interna utilizada para entregar eventos """

        return self._queue

    def start(self, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """ Inicia a thread consumidora mantendo a assinatura ativa.

        Quando ``loop`` não é informado o método tenta usar o *event
        loop* atualmente em execução. O método é idempotente e ignora
        chamadas subsequentes enquanto a thread estiver ativa.
        """

        if self._thread is not None and self._thread.is_alive():
            return

        try:
            self._loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.get_event_loop()

        def _worker() -> None:
            while not self._stop_event.is_set():
                try:
                    client = redis.Redis.from_url(_settings.redis_operational_url, decode_responses=True)
                    pubsub = client.pubsub()
                    pubsub.subscribe(self.channel)
                    logger.info("redis_pubsub_subscribed", channel=self.channel)

                    for message in pubsub.listen():
                        if self._stop_event.is_set():
                            break
                        if message.get("type") != "message":
                            continue
                        data_raw = message.get("data")
                        try:
                            parsed = json.loads(data_raw)
                        except (TypeError, json.JSONDecodeError):
                            logger.warning("redis_pubsub_invalid_payload", channel=self.channel)
                            continue
                        if self._loop is not None and not self._loop.is_closed():
                            self._loop.call_soon_threadsafe(self._queue.put_nowait, parsed)
                except Exception as exc:
                    logger.error("redis_pubsub_listener_error", channel=self.channel, error=str(exc))
                    time.sleep(self.reconnect_interval)

        self._stop_event.clear()
        self._thread = threading.Thread(target=_worker, daemon=True, name=f"redis-sub-{self.channel}")
        self._thread.start()

    async def get(self) -> dict[str, Any]:
        """Aguarda e retorna o próximo evento recebido do canal."""

        return await self._queue.get()

    def stop(self) -> None:
        """Solicita a parada da thread assinante e limpa recursos."""

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        logger.info("redis_pubsub_unsubscribed", channel=self.channel)


__all__ = ["publish_message", "RedisChannelSubscriber"]
