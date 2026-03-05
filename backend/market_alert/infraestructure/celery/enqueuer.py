""" Ponto único de entrada para enfileiramento de coletas no Celery.

``CollectionEnqueuer`` é a única classe que chama ``celery_app.send_task()``
para a fila ``scraping``. Todos os outros módulos que precisam enfileirar uma
coleta devem usar esta classe — nunca chamar ``send_task()`` diretamente.

Responsabilidade única:
    Construir payload tipado, validar, registrar log e enviar para a fila
    Celery. Não contém lógica de negócio, fila Redis nem decisões de retry.

Fluxo:
    caller → CollectionEnqueuer.enqueue_monitored() / enqueue_competitor()
           → build_*_payload() → CollectionPayload
           → CollectionPayload.model_dump(mode='json')
           → celery_app.send_task() → fila 'scraping'
"""

from __future__ import annotations

from uuid import UUID

import structlog
from celery.canvas import Signature

from market_alert.core.config_alert import settings
from market_alert.infraestructure.celery.celery_app import celery_app
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.schemas.schemas_collection_payload import CollectionPayload
from market_alert.collectors.orchestrator.payload_builders import (
    build_competitor_payload,
    build_monitored_payload,
)


logger = structlog.get_logger("collection_enqueuer")

_COLLECT_TASK_NAME = "market_alert.collectors.tasks.collector_product_task.collect_product_task"
_SCRAPING_QUEUE = "scraping"

class CollectionEnqueuer:
    """ Enfileira coletas de monitorados e concorrentes na fila Celery 'scraping'.

    Cada método constrói o ``CollectionPayload`` via builders centralizados,
    serializa para dict e envia para a task de coleta. O ``trace_id`` é gerado
    automaticamente pelo schema se não informado.

    Uso típico::

        enqueuer = CollectionEnqueuer()
        trace = enqueuer.enqueue_monitored(monitored, user_id=user_id)
        # trace é o trace_id usado — útil para correlação de logs
    """

    def enqueue_monitored(
        self,
        monitored: MonitoredProduct,
        user_id: UUID,
        *,
        trace_id: str | None = None,
        countdown: float | None = None,
        on_complete: Signature | None = None,
        on_error: Signature | None = None,
    ) -> str:
        """ Enfileira coleta de monitorado e retorna o trace_id usado.

        Verifica pausa antes de enfileirar — monitorados pausados são
        ignorados silenciosamente com log de diagnóstico.

        Args:
            monitored: instância do monitorado a coletar.
            user_id: UUID do usuário dono do monitorado.
            trace_id: ID de rastreamento (gerado automaticamente se None).
            countdown: atraso em segundos para início da task no Celery.
            on_complete: assinatura Celery para callback de sucesso (link=).
            on_error: assinatura Celery para callback de erro (link_error=).

        Returns:
            trace_id efetivamente usado na coleta.
        """
        if getattr(monitored, "paused", False):
            logger.info(
                "enqueue_skipped_monitored_paused",
                monitored_id=str(monitored.id),
                user_id=str(user_id),
            )
            return trace_id or ""

        payload = build_monitored_payload(monitored, user_id=user_id, trace_id=trace_id)
        self._send(
            payload,
            countdown=countdown,
            on_complete=on_complete,
            on_error=on_error,
        )
        logger.info(
            "enqueue_monitored_dispatched",
            monitored_id=str(monitored.id),
            user_id=str(user_id),
            trace_id=payload.trace_id,
            countdown=countdown,
        )
        return payload.trace_id

    def enqueue_competitor(
        self,
        competitor: CompetitorProduct,
        *,
        user_id: UUID,
        trace_id: str | None = None,
        countdown: float | None = None,
        on_complete: Signature | None = None,
        on_error: Signature | None = None,
    ) -> str:
        """ Enfileira coleta de concorrente e retorna o trace_id usado.

        Args:
            competitor: instância do concorrente a coletar.
            user_id: UUID do usuário dono do monitorado.
            trace_id: ID de rastreamento (gerado automaticamente se None).
            countdown: atraso em segundos para início da task no Celery.
            on_complete: assinatura Celery para callback de sucesso (link=).
            on_error: assinatura Celery para callback de erro (link_error=).

        Returns:
            trace_id efetivamente usado na coleta.
        """
        payload = build_competitor_payload(competitor, user_id=user_id, trace_id=trace_id)
        self._send(
            payload,
            countdown=countdown,
            on_complete=on_complete,
            on_error=on_error,
        )
        logger.info(
            "enqueue_competitor_dispatched",
            competitor_id=str(competitor.id),
            monitored_id=str(competitor.monitored_product_id),
            trace_id=payload.trace_id,
            countdown=countdown,
        )
        return payload.trace_id

    def enqueue_group(
        self,
        monitored: MonitoredProduct,
        competitors: list[CompetitorProduct],
        user_id: UUID,
        *,
        trace_id: str | None = None,
        enqueued_at: str | None = None,
        on_monitored_complete: Signature | None = None,
        on_monitored_error: Signature | None = None,
    ) -> dict[str, str]:
        """ Enfileira monitorado e todos os seus concorrentes com o mesmo trace_id.

        Retorna mapeamento ``{produto_id: trace_id}`` para rastreamento de cada
        item do grupo. O monitorado é enfileirado primeiro; concorrentes seguem
        sem countdown (despacho imediato).

        Args:
            monitored: instância do monitorado raiz.
            competitors: lista de concorrentes ativos vinculados.
            user_id: UUID do usuário dono.
            trace_id: ID de rastreamento compartilhado pelo grupo.
            enqueued_at: ISO timestamp de enfileiramento para métricas de latência.
            on_monitored_complete: callback de sucesso para o monitorado.
            on_monitored_error: callback de erro para o monitorado.

        Returns:
            dict mapeando str(product_id) → trace_id usado.
        """
        monitored_payload = build_monitored_payload(
            monitored,
            user_id=user_id,
            trace_id=trace_id,
            enqueued_at=enqueued_at,
        )
        group_trace_id = monitored_payload.trace_id
        results: dict[str, str] = {}

        self._send(
            monitored_payload,
            on_complete=on_monitored_complete,
            on_error=on_monitored_error,
        )
        results[str(monitored.id)] = group_trace_id

        for competitor in competitors:
            competitor_payload = build_competitor_payload(
                competitor,
                user_id=user_id,
                trace_id=group_trace_id,
                enqueued_at=enqueued_at,
            )
            self._send(competitor_payload)
            results[str(competitor.id)] = group_trace_id

        logger.info(
            "enqueue_group_dispatched",
            monitored_id=str(monitored.id),
            competitors_count=len(competitors),
            trace_id=group_trace_id,
        )
        return results

    def _send(
        self,
        payload: CollectionPayload,
        *,
        countdown: float | None = None,
        on_complete: Signature | None = None,
        on_error: Signature | None = None,
    ) -> None:
        """ Serializa o payload e envia para a fila Celery.

        Este é o único método que chama ``celery_app.send_task()`` para coletas.
        Todos os métodos públicos delegam para cá.
        """
        celery_app.send_task(
            _COLLECT_TASK_NAME,
            kwargs={"payload": payload.model_dump(mode="json")},
            queue=_SCRAPING_QUEUE,
            countdown=countdown,
            link=on_complete,
            link_error=on_error,
        )


__all__ = ["CollectionEnqueuer"]
