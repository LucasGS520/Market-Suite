""" Service Layer de Notificações — ponto único de orquestração.

Este módulo coordena o fluxo completo de notificações:
  avaliação → dedup/cooldown → lock → persistência → enfileiramento

Responsabilidades desta camada:
- Buscar preferências e regras via CRUD
- Chamar o evaluator para gerar candidatos
- Aplicar deduplicação (Redis + banco)
- Aplicar cooldown (Redis + banco)
- Adquirir/liberar locks para prevenir race conditions
- Persistir eventos e notificações via CRUD
- Registrar cooldown Redis após envio bem-sucedido

O que NÃO pertence aqui:
- Lógica de domínio puro (está em notifications/domain/)
- Operações Redis brutas (estão em notifications/infra/)
- Acesso direto a modelos ORM (vai via CRUD)
- Envio direto por canal (vai via task Celery)
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog
from decimal import Decimal
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings
from market_alert.crud.crud_notifications import (
    add_notification_attempt,
    acquire_notification_for_processing,
    create_event_log,
    create_notification,
    get_last_sent_at,
    get_pending_notifications,
    has_dedup_in_window,
    has_recent_sent_notification,
    list_alert_rules,
    list_user_notification_preferences,
    mark_notification_dead_letter,
    mark_notification_failed,
    mark_notification_sent,
    update_alert_rule_last_triggered,
    update_preference_last_notified,
    DEFAULT_MAX_ATTEMPTS,
)
from market_alert.enums.enums_notifications import DeliveryStatus, EventType, NotificationStatus
from market_alert.notifications.domain.cooldown_resolver import is_within_cooldown, resolve_cooldown_seconds
from market_alert.notifications.domain.deduplication import generate_dedup_hash
from market_alert.notifications.evaluator import NotificationCandidate, evaluate
from market_alert.notifications.infra.notification_locks import notification_lock_manager
from market_alert.notifications.infra.redis_repository import notification_redis_repository

if TYPE_CHECKING:
    from market_alert.models import MonitoredProduct, User


logger = structlog.get_logger("services_notifications")

# Janela de deduplicação de envios recentes (em segundos)
_DEDUP_SENT_WINDOW_SECONDS = max(
    getattr(settings, "NOTIFICATION_DEDUPE_SENT_WINDOW_SECONDS", 0),
    600,  # mínimo de 10 minutos
)

# Backoff de retry em segundos por número de tentativa
_RETRY_BACKOFF_SECONDS = {1: 60, 2: 300}


def evaluate_and_create_notifications(
    monitored: "MonitoredProduct",
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
    *,
    user: "User",
    db: Session,
    trace_id: str | None = None,
    source: str = "services_notifications",
) -> list[str]:
    """ Orquestra avaliação, dedup, persistência e enfileiramento de notificações.

    Fluxo para cada candidato gerado pelo evaluator:
    1. Calcula dedup_hash e cooldown_seconds (responsabilidade desta camada)
    2. Verifica cooldown via DB (get_last_sent_at + is_within_cooldown)
    3. Verifica dedup no Redis (marcador de envio recente)
    4. Verifica cooldown no Redis (marcador de cooldown ativo)
    5. Verifica dedup no banco (janela de envios recentes)
    6. Adquire lock para prevenir race conditions
    7. Cria o event_log
    8. Cria a notificação (persiste)
    9. Registra marcadores de dedup e cooldown no Redis
    10. Libera o lock

    Args:
        monitored: Produto monitorado que gerou o evento.
        previous_snapshot: Snapshot anterior para comparação.
        current_snapshot: Snapshot atual com os dados mais recentes.
        user: Usuário dono do produto monitorado.
        db: Sessão de banco de dados.
        trace_id: ID de rastreamento (gerado automaticamente se não fornecido).
        source: Identificador da origem da chamada para logs.

    Returns:
        Lista com os IDs (string) das notificações criadas com sucesso.
    """
    resolved_trace_id = trace_id or str(uuid4())
    now = datetime.now(timezone.utc)

    preferences = list_user_notification_preferences(
        db,
        user_id=monitored.user_id,
        monitored_product_id=monitored.id,
    )
    alert_rules = list_alert_rules(
        db,
        user_id=monitored.user_id,
        monitored_product_id=monitored.id,
    )

    candidates = evaluate(
        monitored,
        previous_snapshot,
        current_snapshot,
        preferences,
        user=user,
        alert_rules=alert_rules,
    )

    if not candidates:
        logger.info(
            "notifications_no_candidates",
            monitored_id=str(monitored.id),
            trace_id=resolved_trace_id,
        )
        return []

    # Agrupa candidatos por tipo de evento para criar um event_log por evento
    candidates_by_event: dict[EventType, list[NotificationCandidate]] = {}
    for candidate in candidates:
        candidates_by_event.setdefault(candidate.event_type, []).append(candidate)

    created_notification_ids: list[str] = []

    for event_type, event_candidates in candidates_by_event.items():
        payload = {
            "monitored_id": str(monitored.id),
            "monitored_url": monitored.product_url,
            "event_type": event_type.value,
            "price": current_snapshot.get("price"),
            "price_previous": (previous_snapshot or {}).get("price"),
            "availability": current_snapshot.get("availability"),
            "summary": current_snapshot.get("summary"),
            "price_delta_percent": current_snapshot.get("price_delta_percent"),
        }

        try:
            event = create_event_log(
                db,
                event_type=event_type,
                trace_id=resolved_trace_id,
                payload=payload,
                source=source,
                monitored_product_id=monitored.id,
                user_id=user.id,
                commit=False,
            )

            for candidate in event_candidates:
                notification_id = _persist_candidate(
                    db,
                    candidate=candidate,
                    event_id=event.id,
                    monitored=monitored,
                    user=user,
                    event_type=event_type,
                    now=now,
                )
                if notification_id is not None:
                    created_notification_ids.append(notification_id)

            db.commit()

        except Exception:
            db.rollback()
            logger.exception(
                "notifications_event_persistence_failed",
                monitored_id=str(monitored.id),
                event_type=event_type.value,
                trace_id=resolved_trace_id,
            )
            raise

    logger.info(
        "notifications_created",
        monitored_id=str(monitored.id),
        count=len(created_notification_ids),
        trace_id=resolved_trace_id,
    )
    return created_notification_ids


def _persist_candidate(
    db: Session,
    *,
    candidate: NotificationCandidate,
    event_id: UUID,
    monitored: "MonitoredProduct",
    user: "User",
    event_type: EventType,
    now: datetime,
) -> str | None:
    """ Verifica dedup/cooldown, adquire lock e persiste uma notificação candidata.

    Esta função é responsável por calcular o dedup_hash e o cooldown_seconds,
    pois esses são detalhes de implementação da camada de serviço, não do evaluator.

    Returns:
        ID da notificação criada como string, ou None se suprimida.
    """
    # Calcula dedup_hash e cooldown_seconds nesta camada (não no evaluator)
    dedup_hash = generate_dedup_hash(
        user_id=str(user.id),
        monitored_id=str(monitored.id),
        event_type=event_type,
    )
    cooldown_seconds = resolve_cooldown_seconds(
        preference=candidate.preference,
        alert_rule=candidate.alert_rule,
        default_cooldown_seconds=settings.DEFAULT_COOLDOWN_SECONDS,
    )

    lock_owner: str | None = None

    # 1. Verifica cooldown via banco (último envio para este produto/canal)
    last_sent_at = get_last_sent_at(
        db,
        monitored_product_id=monitored.id,
        channel=candidate.channel,
    )
    if is_within_cooldown(last_sent_at, cooldown_seconds, now=now):
        logger.debug(
            "notification_suppressed_cooldown_db_last_sent",
            channel=candidate.channel.value,
            monitored_id=str(monitored.id),
        )
        return None

    # 2. Verifica dedup no Redis (marcador de envio recente)
    if notification_redis_repository.has_dedup_marker(dedup_hash):
        logger.debug(
            "notification_suppressed_dedup_redis",
            dedup_hash=dedup_hash,
            channel=candidate.channel.value,
        )
        return None

    # 3. Verifica cooldown no Redis (marcador de cooldown ativo)
    if notification_redis_repository.has_cooldown_marker(
        monitored_product_id=monitored.id,
        channel=candidate.channel,
        event_type=event_type,
    ):
        logger.debug(
            "notification_suppressed_cooldown_redis",
            channel=candidate.channel.value,
            monitored_id=str(monitored.id),
        )
        return None

    # 4. Verifica dedup no banco (janela de envios recentes)
    if has_recent_sent_notification(
        db,
        dedup_hash=dedup_hash,
        window_seconds=_DEDUP_SENT_WINDOW_SECONDS,
        now=now,
    ):
        logger.debug(
            "notification_suppressed_dedup_db",
            dedup_hash=dedup_hash,
            channel=candidate.channel.value,
        )
        return None

    # 5. Verifica duplicata na janela de cooldown no banco
    if has_dedup_in_window(
        db,
        dedup_hash=dedup_hash,
        cooldown_seconds=cooldown_seconds,
        now=now,
    ):
        logger.debug(
            "notification_suppressed_cooldown_db_window",
            dedup_hash=dedup_hash,
            channel=candidate.channel.value,
        )
        return None

    # 6. Adquire lock para prevenir race condition entre workers
    lock_acquired, lock_owner = notification_lock_manager.acquire(dedup_hash, ttl_seconds=60)
    if not lock_acquired:
        logger.debug(
            "notification_suppressed_lock_unavailable",
            dedup_hash=dedup_hash,
            channel=candidate.channel.value,
        )
        return None

    try:
        # 7. Marca dedup no Redis antes de persistir (SET NX — proteção de race)
        if cooldown_seconds > 0:
            if not notification_redis_repository.set_dedup_marker(dedup_hash, cooldown_seconds):
                logger.debug(
                    "notification_suppressed_dedup_redis_race",
                    dedup_hash=dedup_hash,
                )
                return None

        # 8. Persiste a notificação
        notification = create_notification(
            db,
            event_id=event_id,
            user_id=monitored.user_id,
            channel=candidate.channel,
            recipient=candidate.recipient,
            dedup_hash=dedup_hash,
            event_type=event_type,
            alert_id=candidate.alert_rule.id if candidate.alert_rule else None,
            monitored_product_id=monitored.id,
            subject=candidate.subject,
            message=candidate.message,
            payload=candidate.payload,
            priority=candidate.priority,
            cooldown_seconds=cooldown_seconds,
            status=NotificationStatus.pending,
            max_attempts=DEFAULT_MAX_ATTEMPTS,
            commit=False,
        )

        # 9. Atualiza carimbos de disparo em regras e preferências
        if candidate.alert_rule:
            update_alert_rule_last_triggered(
                db,
                alert_rule=candidate.alert_rule,
                triggered_at=now,
                commit=False,
            )
        if candidate.preference:
            update_preference_last_notified(
                db,
                preference=candidate.preference,
                notified_at=now,
                commit=False,
            )

        return str(notification.id)

    finally:
        notification_lock_manager.release(dedup_hash, lock_owner)


def process_notification(
    db: Session,
    *,
    notification_id: UUID,
) -> bool:
    """ Processa uma única notificação pendente: adquire, envia e registra tentativa.

    Fluxo:
    1. Adquire a notificação para processamento (SELECT FOR UPDATE)
    2. Adquire lock Redis para envio exclusivo
    3. Chama o adapter do canal
    4. Registra a tentativa de entrega
    5. Marca como enviada ou falha
    6. Registra cooldown no Redis se enviado com sucesso

    Args:
        db: Sessão de banco de dados.
        notification_id: ID da notificação a processar.

    Returns:
        True se a notificação foi enviada com sucesso, False caso contrário.
    """
    from market_alert.notifications.channels import get_channel_adapter

    with db.begin():
        notification = acquire_notification_for_processing(
            db,
            notification_id=notification_id,
        )
        if notification is None:
            logger.info(
                "notification_processing_skipped",
                notification_id=str(notification_id),
                reason="not_found_or_already_processing",
            )
            return False

    lock_acquired, lock_owner = notification_lock_manager.acquire(
        notification.dedup_hash,
        ttl_seconds=60,
    )
    if not lock_acquired:
        logger.info(
            "notification_processing_skipped",
            notification_id=str(notification_id),
            reason="send_lock_unavailable",
        )
        return False

    start = time.perf_counter()
    success = False

    try:
        adapter = get_channel_adapter(notification.channel)
        payload = {
            "recipient": notification.recipient,
            "subject": notification.subject,
            "message": notification.message,
            "channel": notification.channel.value,
            "payload": notification.payload or {},
        }

        try:
            result = adapter.send(payload)
        except Exception as exc:
            result = {"success": False, "error": "adapter_exception", "raw_response": {"detail": str(exc)}}

        success = bool(result.get("success"))
        latency_ms = int((time.perf_counter() - start) * 1000)
        delivery_status = DeliveryStatus.success if success else DeliveryStatus.failed
        error_code = result.get("error") if not success else None
        error_message = None
        if not success and isinstance(result.get("raw_response"), dict):
            error_message = result["raw_response"].get("detail")

        with db.begin():
            add_notification_attempt(
                db,
                notification_id=notification.id,
                attempt_number=notification.attempts,
                status=delivery_status,
                provider_message_id=str(result.get("provider_id")) if result.get("provider_id") else None,
                provider_response=result.get("raw_response") if isinstance(result.get("raw_response"), dict) else None,
                error_code=error_code,
                error_message=error_message,
                latency_ms=latency_ms,
                commit=False,
            )

            if success:
                mark_notification_sent(db, notification=notification, commit=False)
                # Registra cooldown no Redis após marcar como enviado
                if notification.cooldown_seconds > 0:
                    notification_redis_repository.set_cooldown_marker(
                        monitored_product_id=notification.monitored_product_id,
                        channel=notification.channel,
                        event_type=notification.event_log.event_type,
                        ttl_seconds=notification.cooldown_seconds,
                    )
                logger.info(
                    "notification_sent",
                    notification_id=str(notification.id),
                    channel=notification.channel.value,
                    latency_ms=latency_ms,
                )
            else:
                next_attempt_at = _calculate_next_attempt(
                    notification.attempts,
                    now=datetime.now(timezone.utc),
                )

                if notification.attempts >= notification.max_attempts or next_attempt_at is None:
                    mark_notification_dead_letter(db, notification=notification, commit=False)
                    logger.warning(
                        "notification_dead_lettered",
                        notification_id=str(notification.id),
                        channel=notification.channel.value,
                    )
                else:
                    mark_notification_failed(
                        db,
                        notification=notification,
                        next_attempt_at=next_attempt_at,
                        commit=False,
                    )
                    logger.warning(
                        "notification_send_failed",
                        notification_id=str(notification.id),
                        channel=notification.channel.value,
                        error_code=error_code,
                        attempt=notification.attempts,
                    )

        return success

    finally:
        notification_lock_manager.release(notification.dedup_hash, lock_owner)


def _calculate_next_attempt(attempts: int, *, now: datetime) -> datetime | None:
    """ Calcula o próximo instante de retry com base no backoff configurado.

    Args:
        attempts: Número de tentativas já realizadas.
        now: Instante de referência.

    Returns:
        Datetime do próximo retry, ou None se não há mais retries.
    """
    delay = _RETRY_BACKOFF_SECONDS.get(attempts)
    if delay is None:
        return None
    return now + timedelta(seconds=delay)


def enqueue_pending_notifications(
    db: Session,
    notification_ids: list[str] | None = None,
    *,
    limit: int = 200,
    trace_id: str | None = None,
) -> int:
    """ Busca notificações pendentes e enfileira cada uma para envio assíncrono.

    Ponto único de enfileiramento de notificações. Encapsula a busca de
    pendentes, normalização de IDs e dispatch para ``send_notification_task``.

    O dispatch usa ``TaskEnqueuer`` para evitar
    dependência circular entre este módulo e o módulo de tasks.

    Args:
        db: Sessão ativa de banco injetada pela camada chamadora.
        notification_ids: Lista de IDs específicos para enfileirar. Quando
            ``None``, busca todas as notificações pendentes elegíveis no banco.
        limit: Número máximo de notificações a enfileirar por chamada.
        trace_id: ID de rastreamento para correlação de logs.

    Returns:
        Número de notificações efetivamente enfileiradas.
    """
    resolved_trace_id = trace_id or str(uuid4())
    now = datetime.now(timezone.utc)
    ids = [UUID(nid) for nid in notification_ids] if notification_ids else None

    from market_alert.services.task_enqueuer import TaskEnqueuer
    enqueuer = TaskEnqueuer()

    pending = get_pending_notifications(db, limit=limit, now=now, notification_ids=ids)
    count = 0
    for notification in pending:
        enqueuer.enqueue_notification(notification.id, trace_id=resolved_trace_id)
        count += 1

    logger.info(
        "notifications_enqueued",
        count=count,
        trace_id=resolved_trace_id,
        notification_ids=notification_ids,
    )
    return count
