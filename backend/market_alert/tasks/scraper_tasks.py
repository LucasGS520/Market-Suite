""" Wrapper legado para tarefas de scraping.

A lógica principal foi movida para ``market_alert.tasks.collector_tasks``.
Este módulo mantém aliases mínimos para compatibilidade com imports
antigos em testes e serviços, garantindo que chamadas existentes passem
pela task centralizada.
"""

from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from market_alert.core.celery_app import celery_app
from market_alert.tasks.collector_tasks import collect_product_task


def _merge_competitor_payload(
    payload: Mapping[str, Any] | None,
    monitored_product_id: str | UUID | None,
    url: str | None,
    **legacy_kwargs,
) -> dict[str, Any]:
    """ Normaliza o payload para reutilizar a task central """
    merged: dict[str, Any] = {"kind": "competitor"}
    merged.update(payload or {})
    merged.setdefault("monitored_id", monitored_product_id or legacy_kwargs.get("monitored_id"))
    merged.setdefault("url", url or legacy_kwargs.get("url"))
    if legacy_kwargs.get("owner_id"):
        merged["user_id"] = legacy_kwargs["owner_id"]
    return merged

@celery_app.task(name="collect_competitor_task", queue="scraping")
def collect_competitor_task(
    self,
    payload: Mapping[str, Any] | None = None,
    monitored_product_id: str | None = None,
    url: str | None = None,
    **legacy_kwargs,
):
    """Redireciona coletas de concorrentes para a task centralizada."""
    normalized = _merge_competitor_payload(payload, monitored_product_id, url, **legacy_kwargs)
    return collect_product_task.run(payload=normalized)

__all__ = ["collect_product_task", "collect_competitor_task"]
