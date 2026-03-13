""" Reconciliador de workflows Temporal por monitorado ativo.

Garante convergência: nenhum monitorado ativo (paused=False) pode ficar
sem workflow após boot, falha de infra ou lacuna de estado.

Idempotência garantida: chamar reconcile_all() duas vezes não cria
workflows duplicados — o Temporal impede via workflow_id estável +
id_reuse_policy=ALLOW_DUPLICATE_FAILED_ONLY.
"""
from __future__ import annotations

import structlog

from market_orchestrator.alert.alert_client import TemporalOrchestrationClient
from market_orchestrator.schemas.schemas_workflow import CollectionPolicy, WorkflowInput


logger = structlog.get_logger("orchestrator.reconciler")

class WorkflowReconciler:
    """ Reconciliador de estado entre PostgreSQL e Temporal.

    Para cada monitorado ativo (paused=False), verifica se há workflow vivo.
    Se não houver, cria via signal_with_start (idempotente).
    """

    def __init__(self, client: TemporalOrchestrationClient | None = None) -> None:
        self._client = client or TemporalOrchestrationClient()

    def reconcile_all(self) -> dict[str, int]:
        """ Reconcilia todos os monitorados ativos.

        Retorna dict com contadores: total, started, alive, errors.
        """
        from shared.infra.db.database import SessionLocal
        from market_alert.models.models_products import MonitoredProduct

        counts = {"total": 0, "started": 0, "alive": 0, "errors": 0}

        db = SessionLocal()
        try:
            actives = (
                db.query(
                    MonitoredProduct.id,
                    MonitoredProduct.user_id,
                    MonitoredProduct.check_interval,
                )
                .filter(MonitoredProduct.paused.is_(False))
                .all()
            )
        except Exception as exc:
            logger.error("reconciler_db_query_failed", error=str(exc))
            db.close()
            return counts
        finally:
            db.close()

        counts["total"] = len(actives)
        logger.info("reconciler_started", total_active=counts["total"])

        for row in actives:
            monitored_id = str(row.id)
            user_id = str(row.user_id)
            interval = row.check_interval or 3600

            try:
                snapshot = self._client.query_sync(monitored_id)

                if snapshot is not None:
                    counts["alive"] += 1
                    continue

                #Workflow não encontrado — cria via signal_with_start
                workflow_input = WorkflowInput(
                    monitored_id=monitored_id,
                    user_id=user_id,
                    policy=CollectionPolicy(interval_seconds=interval),
                    bootstrap_flags={"is_reconciliation": True},
                )
                ok = self._client.signal_with_start_sync(workflow_input)
                if ok:
                    counts["started"] += 1
                    logger.info(
                        "reconciler_workflow_started",
                        monitored_id=monitored_id,
                    )
                else:
                    counts["errors"] += 1

            except Exception as exc:
                counts["errors"] += 1
                logger.error(
                    "reconciler_workflow_error",
                    monitored_id=monitored_id,
                    error=str(exc),
                )

        logger.info(
            "reconciler_finished",
            total=counts["total"],
            started=counts["started"],
            alive=counts["alive"],
            errors=counts["errors"],
        )
        return counts
