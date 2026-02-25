""" Ponto único de enfileiramento para tasks de comparação e notificação.

``TaskEnqueuer`` centraliza os ``send_task()`` de domínios que não são coleta.
Para coletas, use ``CollectionEnqueuer`` (``orchestrator/collection_enqueuer.py``).

Responsabilidade única:
    Serializar parâmetros, registrar log e chamar ``celery_app.send_task()``.
    Nenhuma lógica de negócio, debounce ou decisão de retry aqui.

Uso típico::

    enqueuer = TaskEnqueuer()
    enqueuer.enqueue_comparison(monitored_id, reason="material_change")
    enqueuer.enqueue_notification(notification_id)

Não chame ``celery_app.send_task()`` diretamente fora desta classe
(para comparações e notificações) — sempre use este wrapper.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from market_alert.core.celery_app import celery_app

logger = structlog.get_logger("task_enqueuer")

_COMPARE_TASK = "market_alert.tasks.compare_prices_task.compare_prices_task"
_NOTIFICATION_TASK = "market_alert.tasks.send_notification_task.send_notification_task"
_COMPARE_QUEUE = "compare"
_NOTIFICATION_QUEUE = "notifications"


class TaskEnqueuer:
    """ Enfileira tasks de comparação e notificação na fila Celery correta.

    Cada método constrói os argumentos, registra log de diagnóstico e
    envia para a fila via ``celery_app.send_task()``. Erros de enfileiramento
    são propagados ao chamador para tratamento explícito.
    """

    @staticmethod
    def _build_trace_headers(trace_id: str | None) -> dict[str, str]:
        """ Monta headers padrão para preservar rastreabilidade no worker
        
        O trace_id é enviado no header para facilitar correlação mesmo quando a
        assinatura da task muda no futuro. Quando ausente, retorna dicionário
        vazio para evitar ruído no trasnporte.
        """
        if not trace_id:
            return {}
        return {"trace_id": trace_id}

    def enqueue_comparison(
        self,
        monitored_id: UUID | str,
        *,
        reason: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """ Enfileira comparação de preços para um monitorado.

        Args:
            monitored_id: UUID do produto monitorado a comparar.
            reason: Motivo da comparação (usado apenas em logs).
            trace_id: ID de rastreamento para correlação de logs.
        """
        monitored_id_str = str(monitored_id)
        celery_app.send_task(
            _COMPARE_TASK,
            args=[monitored_id_str],
            kwargs={"trace_id": trace_id},
            #Duplicamos trace_id em kwargs + headers para cobrir observabilidade e fallback em rotas que não leem parâmetros explicitamente.
            headers=self._build_trace_headers(trace_id),
            queue=_COMPARE_QUEUE,
        )
        logger.info(
            "comparison_enqueued",
            monitored_id=monitored_id_str,
            reason=reason,
            trace_id=trace_id,
        )

    def enqueue_notification(
        self,
        notification_id: UUID | str,
        *,
        trace_id: str | None = None,
    ) -> None:
        """ Enfileira envio de uma notificação específica.

        Args:
            notification_id: UUID da notificação a enviar.
            trace_id: ID de rastreamento para correlação de logs.
        """
        notification_id_str = str(notification_id)
        celery_app.send_task(
            _NOTIFICATION_TASK,
            args=[notification_id_str],
            kwargs={"trace_id": trace_id},
            #Mantém padrão único de propagação para todos os wrappers.
            headers=self._build_trace_headers(trace_id),
            queue=_NOTIFICATION_QUEUE,
        )
        logger.info(
            "notification_enqueued",
            notification_id=notification_id_str,
            trace_id=trace_id,
        )


__all__ = ["TaskEnqueuer"]
