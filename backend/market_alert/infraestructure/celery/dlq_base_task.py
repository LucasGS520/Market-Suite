""" Classe base para tasks que devem enviar falhas permanentes para a DLQ.

Quando uma task Celery herda de ``DLQTask`` via ``base=DLQTask``, o método
``on_failure`` é chamado automaticamente pelo worker após a task falhar e
não poder mais ser reexecutada (retries esgotados). A falha é então
encaminhada para a fila ``dead_letter`` para registro e auditoria.

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

``self.app`` é usado em vez de importar ``celery_app`` diretamente para
evitar importação circular (celery_app.py importa os módulos de tasks).
"""

from __future__ import annotations

import structlog
from celery import Task

from shared.utils import sanitize_exception_message

logger = structlog.get_logger("dlq_base_task")


class DLQTask(Task):
    """ Task base que registra falhas permanentes na fila dead_letter.

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
        """ Envia task para a DLQ após falha permanente (retries esgotados). """
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

        try:
            self.app.send_task(
                "market_alert.infra.celery.dlq_handler.handle_dead_letter",
                kwargs={
                    "task_name": self.name,
                    "task_id": task_id,
                    "exception_class": type(exc).__name__,
                    "exception_message": sanitize_exception_message(str(exc), max_length=500),
                    "retry_count": retry_count,
                    "trace_id": trace_id,
                },
                queue="dead_letter",
            )
            logger.warning(
                "task_sent_to_dlq",
                task_name=self.name,
                task_id=task_id,
                exception=type(exc).__name__,
                retry_count=retry_count,
                trace_id=trace_id,
            )
        except Exception:
            #Nunca deixa a DLQ propagar erro — a task já falhou
            logger.exception(
                "dlq_send_failed",
                task_name=self.name,
                task_id=task_id,
            )


__all__ = ["DLQTask"]
