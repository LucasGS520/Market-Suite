""" Task dedicada ao envio de notificações por canal.

Casca fina que delega toda a lógica de envio, retry e registro de tentativas
para services_notifications.process_notification().

Semântica de entrega (Decisão 6): **exactly-once** obrigatório.

- Duplicação causa dano direto: notificação duplicada gera experiência ruim
  para o usuário final (email/SMS/push redundante).
- Mecanismo de proteção (em ``process_notification()``)::

    1. dedup_hash (SHA-256 de user_id + product_id + preço + canal)
    2. Marcador Redis SET NX: ``notifications:dedup:{hash}`` (TTL=cooldown_seconds)
    3. Verificação no banco dentro da janela de deduplicação
    4. Lock por hash: ``lock:{env}:notify:{hash}`` (TTL=60s) para proteção de race

- Esta task é idempotente ao ser reenfileirada: se o marcador Redis ainda
  estiver ativo, ``process_notification()`` suprime silenciosamente e retorna
  False sem efeito colateral.
"""

from __future__ import annotations

from uuid import UUID
import structlog

from shared.infra.db import SessionLocal
from shared.utils.trace_context import set_trace_id

from market_alert.infraestructure.celery.celery_app import celery_app
from market_alert.infraestructure.celery.dlq_base_task import DLQTask
from market_alert.infraestructure.celery.retry_policies import NOTIFICATION_RETRY
from market_alert.notifications.services.services_notifications import process_notification


logger = structlog.get_logger("notifications_send")

@celery_app.task(
    bind=True,
    base=DLQTask,
    **NOTIFICATION_RETRY,
)
def send_notification_task(self, notification_id: str, trace_id: str | None = None) -> None:
    """ Realiza o envio de notificação com propagação explícita de trace_id.

    O ``trace_id`` pode chegar por kwargs (caminho padrão do ``TaskEnqueuer``)
    ou por headers, mantendo compatibilidade com enfileiradores legados.
    """
    request_headers = getattr(self.request, "headers", None) or {}
    resolved_trace_id = trace_id or request_headers.get("trace_id")
    set_trace_id(resolved_trace_id or self.request.id or notification_id)
    task_logger = logger.bind(task_id=self.request.id, notification_id=notification_id)

    with SessionLocal() as db:
        success = process_notification(db, notification_id=UUID(notification_id))

    if not success:
        task_logger.info(
            "notification_send_skipped_or_failed",
            notification_id=notification_id,
        )
