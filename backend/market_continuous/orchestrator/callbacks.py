""" Callbacks padronizados para o ciclo de vida de coletas.

``CollectionCallbacks`` centraliza o que acontece após uma coleta terminar —
seja com sucesso ou erro. No fluxo standalone, os callbacks são chamados
diretamente pelo loop em ``manager.py`` após ``AsyncResult.get()``.
"""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)

class CollectionCallbacks:
    """ Centraliza callbacks de sucesso e erro para coletas de produtos. """

    @staticmethod
    def on_collection_success(
        collect_result: dict,
        monitored_id: str,
        trace_id: str | None = None,
    ) -> None:
        """ Log de sucesso. O reenqueue é gerenciado diretamente por manager.py. """
        from market_alert.collectors.utils.collector_result import _parse_collect_result

        normalized = _parse_collect_result(collect_result)
        logger.info(
            "collection_callback_success",
            extra={
                "monitored_id": monitored_id,
                "outcome": normalized.get("outcome"),
                "reason": normalized.get("reason"),
                "trace_id": trace_id,
            },
        )

    @staticmethod
    def on_collection_error(
        monitored_id: str,
        trace_id: str | None = None,
        reason: str = "collect_task_exception",
    ) -> None:
        """ Log de erro. O reenqueue é gerenciado diretamente por manager.py. """
        logger.warning(
            "collection_callback_error",
            extra={
                "monitored_id": monitored_id,
                "reason": reason,
                "trace_id": trace_id,
            },
        )


__all__ = ["CollectionCallbacks"]
