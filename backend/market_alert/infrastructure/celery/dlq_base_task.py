""" Classe base para tasks que devem enviar falhas permanentes para a DLQ.

Quando uma task Celery herda de ``DLQTask`` via ``base=DLQTask``, o método
``on_failure`` é chamado automaticamente pelo worker após a task falhar e
não poder mais ser reexecutada (retries esgotados). A falha é então
gravada diretamente no Redis Stream configurado em ``CELERY_DLQ_STREAM_NAME``.

Uso::

    @celery_app.task(
        bind=True,
        base=DLQTask,
        name="...",
        queue="scraping",
        **COLLECTION_RETRY,
    )
    def collect_product_task(self, payload):
        ...
"""

from __future__ import annotations

import structlog
from celery import Task

from market_alert.infrastructure.celery.redis_dlq_handler import write_to_dlq

logger = structlog.get_logger("dlq_base_task")


class DLQTask(Task):
    """ Task base que registra falhas permanentes via Redis Streams.

    Apenas tasks com ``max_retries > 0`` utilizam a DLQ; tasks sem política
    de retry já tratam seus próprios erros e não precisam de DLQ.
    """

    abstract = True

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo,
    ) -> None:
        """ Grava falha permanente no Redis Stream DLQ. """
        max_retries = getattr(self, "max_retries", None)
        if not max_retries:
            #Tasks sem política de retry não usam DLQ
            return

        retry_count = getattr(self.request, "retries", 0)

        #Tenta extrair trace_id do primeiro argumento (payload dict) ou kwargs
        trace_id: str | None = None
        if args and isinstance(args[0], dict):
            trace_id = args[0].get("trace_id")
        if trace_id is None:
            trace_id = kwargs.get("trace_id")
        if trace_id is None:
            #Fallback para tarefas que propagam trace_id somente via headers.
            request_headers = getattr(self.request, "headers", None) or {}
            trace_id = request_headers.get("trace_id")
        if trace_id is None:
            #Último fallback: usa o id da requisição Celery para não perder correlação.
            trace_id = getattr(self.request, "id", None)

        #Fila de destino da task (informativa no evento DLQ)
        queue = getattr(self.request, "delivery_info", {}).get("routing_key", "unknown")

        write_to_dlq(
            task_id=task_id,
            task_name=self.name,
            queue=queue,
            exception=exc,
            trace_id=trace_id,
            retry_count=retry_count,
            max_retries=max_retries,
        )


__all__ = ["DLQTask"]
