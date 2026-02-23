""" Wrapper legado para tarefas de scraping.

A lógica principal foi movida para ``market_alert.tasks.collector_product_task``.
Este módulo mantém aliases mínimos para compatibilidade com imports
antigos em testes e serviços, garantindo que chamadas existentes passem
pela task centralizada.

Nota: este módulo será deletado na Fase 6 da refatoração de orquestração.
"""

from __future__ import annotations

from typing import Any, Mapping

from market_alert.core.celery_app import celery_app
from market_alert.tasks.collector_product_task import collect_product_task


@celery_app.task(bind=True, name="collect_competitor_task", queue="scraping")
def collect_competitor_task(
    self,
    payload: Mapping[str, Any] | None = None,
    monitored_product_id: str | None = None,
    url: str | None = None,
    **legacy_kwargs,
):
    """ Redireciona coletas de concorrentes para a task centralizada.

    Optamos por enfileirar a task real para preservar headers, roteamento e
    cadeia de callbacks do Celery, evitando executar a lógica principal
    inline via ``run``.
    """
    #Normalização inline — lógica equivalente ao antigo _merge_competitor_payload()
    normalized: dict[str, Any] = {"kind": "competitor"}
    normalized.update(payload or {})
    normalized.setdefault("monitored_id", monitored_product_id or legacy_kwargs.get("monitored_id"))
    normalized.setdefault("url", url or legacy_kwargs.get("url"))
    if legacy_kwargs.get("owner_id"):
        normalized["user_id"] = legacy_kwargs["owner_id"]

    delivery_info = getattr(self.request, "delivery_info", {}) or {}
    queue = delivery_info.get("routing_key") or delivery_info.get("queue") or "scraping"

    return collect_product_task.apply_async(
        kwargs={"payload": normalized},
        queue=queue,
        headers=getattr(self.request, "headers", None),
    )


__all__ = ["collect_product_task", "collect_competitor_task"]
