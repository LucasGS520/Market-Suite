""" Gerenciamento do ciclo de vida e lógica de execução do coletor contínuo.

Responsável por:
- Decidir se o autostart do coletor contínuo está habilitado (via env)
- Executar loop continuo de consumo da fila de monitorados
- Gerenciar o lock Redis que previne múltiplas instâncias simultâneas
- Gerenciar o cooldown pós-falha para evitar reinícios em loop
- Disparar a task ``run_continuous_collector`` quando necessário
- Manter o loop de revalidação em thread para recuperação automática

Esta lógica estava misturada com a configuração do Celery em ``celery_app.py``.
Extrair aqui permite testar o comportamento operacional isoladamente, sem
precisar instanciar a aplicação Celery completa.

Dependências externas:
    - Redis (via ``get_redis_client`` / ``set_key_with_ttl``)
    - Celery control inspect (para detectar tasks ativas)
    - Variáveis de ambiente (configuração de TTL e flags)
"""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING, Any

import structlog
from billiard.exceptions import TimeLimitExceeded
from celery.exceptions import SoftTimeLimitExceeded

from shared.utils.redis_client import get_redis_client, set_key_with_ttl
from shared.utils.redis_client import is_scraping_suspended
from shared.utils.redis_locks import (
    acquire_continuous_collector_lock,
    refresh_continuous_collector_lock,
    release_continuous_collector_lock,
)

from market_alert.core.config_alert import settings
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.collectors.domain.collection_queue import CollectionQueue
from market_alert.collectors.utils.collector_result import _parse_collect_result
from market_alert.collectors.utils.continuous_dispatch import (
    CollectDispatchDecision,
    _collect_group,
    _handle_processing_requeue,
    _load_monitored,
    _requeue_monitored,
    _should_abort,
)
from market_alert.products.utils.interval_calculator_products import _parse_next_retry_at, _utc_now

if TYPE_CHECKING:
    from celery import Celery
    from sqlalchemy.orm import Session


logger = structlog.get_logger("continuous_collector_manager")

# Chaves Redis usadas pelo gerenciador
_AUTOSTART_KEY = "market_alert:continuous_collector:autostart"
_COOLDOWN_KEY = "market_alert:continuous_collector:autostart:cooldown"
_TASK_NAME = "market_alert.collectors.tasks.continuous_collector_task.run_continuous_collector"
_MONITOR_QUEUE = "monitor"

# Referência ao monotonic de início do processo, injetada por `celery_app.py`
_process_start_monotonic: float = time.monotonic()

def set_process_start_monotonic(value: float) -> None:
    """ Permite que ``celery_app.py`` injete o timestamp de início do processo. """
    global _process_start_monotonic
    _process_start_monotonic = value

def _get_process_uptime_seconds() -> float:
    """ Retorna o uptime do processo em segundos usando relógio monotônico. """
    return round(time.monotonic() - _process_start_monotonic, 2)

def finalize_processing_requeue(
    *,
    db: Session,
    collect_result: Any,
    monitored_id: str,
    trace_id: str | None = None,
) -> None:
    """ Finaliza uma coleta bem-sucedida/normal e retorna o item para a fila
    
    Mantém a lógica de parse e de requeue fora do módulo Celery para reduzir
    acoplamento entre camada de transporte (task) e regra operacional.
    """
    normalized = _parse_collect_result(collect_result)
    next_retry_at = _parse_next_retry_at(normalized.get("next_retry_at"))
    _handle_processing_requeue(
        db=db,
        monitored_id=monitored_id,
        collect_outcome=normalized.get("outcome"),
        reason=normalized.get("status") or normalized.get("reason") or normalized.get("outcome") or "unknown",
        trace_id=trace_id,
        next_retry_at=next_retry_at,
    )

def finalize_processing_requeue_error(
    *,
    db: Session,
    monitored_id: str,
    trace_id: str | None = None,
) -> None:
    """Finaliza uma coleta que falhou e reabilita nova tentativa no fluxo."""
    _handle_processing_requeue(
        db=db,
        monitored_id=monitored_id,
        collect_outcome=None,
        reason="collect_task_exception",
        trace_id=trace_id,
    )

def run_collection_loop(*, db: "Session", task_request: Any, task_id: str | None = None) -> None:
    """ Executa o loop contínuo de consumo da fila de monitorados.

    A task Celery chama esta função para manter a lógica operacional em um
    único serviço, evitando duplicidade de responsabilidades no módulo de task.
    """
    bound_logger = logger.bind(task_id=task_id)
    started_at = time.monotonic()
    queue = CollectionQueue()
    batch_size = max(1, int(settings.CONTINUOUS_WORKER_BATCH_SIZE))
    processing_ttl = int(settings.CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS)
    poll_interval = float(settings.CONTINUOUS_WORKER_POLL_INTERVAL)
    lock_ttl_seconds = int(settings.CONTINUOUS_COLLECTOR_LOCK_TTL_SECONDS)
    lock_refresh_interval = max(1.0, lock_ttl_seconds / 2)

    # Mantém garantia de singleton do loop mesmo com disparos concorrentes.
    lock_acquired, lock_owner = acquire_continuous_collector_lock(
        ttl_seconds=lock_ttl_seconds,
    )
    if not lock_acquired:
        bound_logger.warning("continuous_collector_lock_denied", lock_owner=lock_owner)
        return

    last_lock_refresh = time.monotonic()

    try:
        # A sessão vem da task de entrada para obedecer a regra de sessão única.
        while True:
            processed_ids: list[str] = []
            if _should_abort(task_request):
                bound_logger.warning("continuous_worker_aborted")
                return

            if time.monotonic() - last_lock_refresh >= lock_refresh_interval:
                if not refresh_continuous_collector_lock(
                    owner_id=lock_owner,
                    ttl_seconds=lock_ttl_seconds,
                ):
                    bound_logger.warning(
                        "continuous_collector_lock_lost",
                        lock_owner=lock_owner,
                    )
                    return
                last_lock_refresh = time.monotonic()

            try:
                if is_scraping_suspended():
                    bound_logger.warning("continuous_scraping_suspended")
                    time.sleep(poll_interval)
                    continue

                if not queue.is_available():
                    bound_logger.error("continuous_queue_unavailable")
                    time.sleep(poll_interval)
                    continue

                queue_size = queue.size()
                ready_total = queue.ready_count()
                bound_logger.info(
                    "continuous_loop_iteration",
                    queue_size=queue_size,
                    ready_total=ready_total,
                    timestamp=_utc_now().isoformat(),
                )

                reclaimed = queue.reclaim_stale_items(processing_ttl)
                if reclaimed:
                    # Reencaminha itens presos em processamento para nova tentativa.
                    bound_logger.warning(
                        "continuous_processing_reclaimed",
                        reclaimed_count=len(reclaimed),
                    )

                for _ in range(batch_size):
                    next_id = queue.pop_next_for_collection()
                    if not next_id:
                        break

                    monitored = _load_monitored(db, next_id)
                    if monitored is None:
                        bound_logger.warning("continuous_monitored_missing", monitored_id=next_id)
                        processed_ids.append(next_id)
                        continue

                    if monitored.paused or monitored.status in {MonitoredStatus.failed}:
                        bound_logger.info("continuous_skipped_paused", monitored_id=str(monitored.id))
                        processed_ids.append(str(monitored.id))
                        continue

                    enqueued_at = queue.get_enqueued_at(next_id)
                    try:
                        decision = _collect_group(
                            db=db,
                            monitored=monitored,
                            enqueued_at=enqueued_at,
                        )
                    except Exception:
                        db.rollback()
                        decision = CollectDispatchDecision(
                            outcome="error",
                            next_check_at=_utc_now(),
                            should_requeue=True,
                            retain_processing=False,
                        )
                        bound_logger.exception("continuous_group_failed", monitored_id=str(monitored.id))

                    if not decision.retain_processing:
                        processed_ids.append(str(monitored.id))

                    if decision.should_requeue:
                        requeue_success, _ = _requeue_monitored(
                            monitored=monitored,
                            next_check_at=decision.next_check_at,
                            queue=queue,
                        )
                        if not requeue_success:
                            bound_logger.warning(
                                "requeue_failed_but_retained",
                                monitored_id=str(monitored.id),
                            )
                            if processed_ids and processed_ids[-1] == str(monitored.id):
                                processed_ids.pop()

                    bound_logger.info(
                        "continuous_item_processed",
                        monitored_id=str(monitored.id),
                        outcome=decision.outcome,
                    )

                if processed_ids:
                    queue.mark_as_done(processed_ids)
                time.sleep(poll_interval)

            except TimeLimitExceeded:
                bound_logger.warning(
                    "limit_time_collector_exceeded",
                    uptime_seconds=round(time.monotonic() - started_at, 2),
                    reason="time_limit",
                )
                time.sleep(poll_interval)
                continue
            except SoftTimeLimitExceeded:
                bound_logger.warning(
                    "continuous_soft_time_limit_exceeded",
                    uptime_seconds=round(time.monotonic() - started_at, 2),
                    reason="soft_time_limit",
                )
                time.sleep(poll_interval)
                continue
            except Exception:
                db.rollback()
                bound_logger.exception("continuous_loop_error")
                time.sleep(poll_interval)
    finally:
        release_continuous_collector_lock(owner_id=lock_owner)

# ---------------------------------------------------------------------------
# Funções de estado — verificam flags e Redis
# ---------------------------------------------------------------------------

def autostart_enabled() -> bool:
    """ Retorna True se o autostart do coletor contínuo está habilitado via env. """
    flag = os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART", "0").strip().lower()
    return flag in {"1", "true", "yes"}

def _in_cooldown() -> bool:
    """ Retorna True se há cooldown ativo (chave Redis presente). """
    client = get_redis_client()
    if client is None:
        logger.warning("continuous_autostart_cooldown_check_skipped", reason="redis_unavailable")
        return False
    try:
        return bool(client.exists(_COOLDOWN_KEY))
    except Exception:
        logger.exception("continuous_autostart_cooldown_check_failed")
        return False

def _is_active(celery_app: "Celery") -> bool:
    """ Verifica se há execução ativa do coletor contínuo nos workers Celery. """
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        active_tasks = inspect.active() or {}
    except Exception:
        logger.exception("continuous_autostart_inspect_failed")
        return False

    for tasks in active_tasks.values():
        for task in tasks or []:
            if task.get("name") == _TASK_NAME:
                return True
    return False


# ---------------------------------------------------------------------------
# Funções de escrita — modificam estado no Redis
# ---------------------------------------------------------------------------

def _register_cooldown(*, reason: str) -> None:
    """ Registra cooldown pós-falha para bloquear reinícios consecutivos. """
    cooldown_seconds = int(os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART_COOLDOWN_SECONDS", "120"))
    result = set_key_with_ttl(
        _COOLDOWN_KEY,
        value="1",
        ttl_seconds=cooldown_seconds,
        only_if_absent=True,
    )
    if result is None:
        logger.warning(
            "continuous_autostart_cooldown_unavailable",
            reason="redis_unavailable",
            detail=reason,
        )
        return
    logger.info(
        "continuous_autostart_cooldown_registered",
        ttl_seconds=cooldown_seconds,
        detail=reason,
    )

def _delete_lock() -> None:
    """ Remove o lock de autostart para evitar bloqueios indevidos após falha. """
    client = get_redis_client()
    if client is None:
        logger.warning("continuous_autostart_lock_delete_skipped", reason="redis_unavailable")
        return
    try:
        client.delete(_AUTOSTART_KEY)
    except Exception:
        logger.exception("continuous_autostart_lock_delete_failed")


# ---------------------------------------------------------------------------
# Ação principal — disparar o coletor contínuo
# ---------------------------------------------------------------------------

def request_start(celery_app: "Celery", *, action: str = "triggered") -> None:
    """ Dispara ``run_continuous_collector`` uma única vez quando habilitado.

    Protegido por lock Redis com TTL para prevenir múltiplos disparos
    simultâneos quando vários workers sobem ao mesmo tempo.

    Args:
        celery_app: Instância da aplicação Celery (injetada para evitar import
            circular com ``celery_app.py``).
        action: Rótulo usado nos logs para identificar a origem do disparo
            (``'triggered'``, ``'reactivated'``, etc.).
    """
    if not autostart_enabled():
        return

    if _in_cooldown():
        logger.warning(
            "continuous_autostart_blocked",
            detail="reinício bloqueado por cooldown",
            task_id=None,
            uptime_seconds=_get_process_uptime_seconds(),
            reason="cooldown",
            message="Autostart do coletor contínuo bloqueado pelo cooldown configurado.",
        )
        return

    ttl_seconds = int(os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART_TTL", "60"))
    logger.info("continuous_autostart_requested", ttl_seconds=ttl_seconds)

    lock_result = set_key_with_ttl(
        _AUTOSTART_KEY,
        value="1",
        ttl_seconds=ttl_seconds,
        only_if_absent=True,
    )
    if lock_result is False:
        logger.info("continuous_autostart_skipped", reason="already_running")
        return
    if lock_result is None:
        # Ainda tenta disparar para evitar ficar sem coletas em cenários instáveis
        logger.warning("continuous_autostart_lock_unavailable")

    try:
        async_result = celery_app.send_task(_TASK_NAME, queue=_MONITOR_QUEUE)
        logger.info(
            "continuous_autostart_triggered",
            action=action,
            task_id=async_result.id,
            uptime_seconds=_get_process_uptime_seconds(),
            reason=action,
            message="Autostart do coletor contínuo disparado com sucesso.",
        )
    except Exception:
        _delete_lock()
        _register_cooldown(reason="falha ao iniciar coletor contínuo")
        logger.exception("continuous_autostart_failed")


# ---------------------------------------------------------------------------
# Loop de revalidação — thread de background para recuperação automática
# ---------------------------------------------------------------------------

def _revalidate(celery_app: "Celery") -> None:
    """ Verifica se o coletor contínuo ainda está ativo e reativa se necessário.

    Chamado periodicamente pelo loop de revalidação. Renova o lock quando o
    coletor está ativo; remove lock orfão e reativa quando não está.
    """
    if not autostart_enabled():
        return

    if _is_active(celery_app):
        ttl_seconds = int(os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART_TTL", "60"))
        set_key_with_ttl(
            _AUTOSTART_KEY,
            value="1",
            ttl_seconds=ttl_seconds,
            only_if_absent=False,  # Renova mesmo se já existir
        )
        return

    client = get_redis_client()
    if client is None:
        logger.warning("continuous_autostart_recheck_skipped", reason="redis_unavailable")
        return

    try:
        has_lock = bool(client.exists(_AUTOSTART_KEY))
    except Exception:
        logger.exception("continuous_autostart_recheck_failed")
        return

    if has_lock:
        # Remove lock orfão antes de tentar reativar a task
        _delete_lock()

    logger.warning("continuous_autostart_reactivated")
    request_start(celery_app, action="reactivated")

def start_revalidation_loop(celery_app: "Celery") -> None:
    """ Inicia thread daemon de revalidação periódica do coletor contínuo.

    Executa apenas se ``CONTINUOUS_COLLECTOR_AUTOSTART=1``. O intervalo é
    controlado por ``CONTINUOUS_COLLECTOR_AUTOSTART_RECHECK_INTERVAL`` (padrão
    30 segundos).

    Args:
        celery_app: Instância da aplicação Celery para inspeção de tasks ativas.
    """
    if not autostart_enabled():
        return

    interval_seconds = int(os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART_RECHECK_INTERVAL", "30"))

    def _loop() -> None:
        while True:
            time.sleep(interval_seconds)
            _revalidate(celery_app)

    thread = threading.Thread(
        target=_loop,
        name="continuous_autostart_revalidation_loop",
        daemon=True,
    )
    thread.start()
    logger.info(
        "continuous_autostart_revalidation_loop_started",
        interval_seconds=interval_seconds,
    )
