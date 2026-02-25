""" Gerenciamento do ciclo de vida do coletor contínuo.

Responsável por:
- Decidir se o autostart do coletor contínuo está habilitado (via env)
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
from typing import TYPE_CHECKING

import structlog
from shared.utils.redis_client import get_redis_client, set_key_with_ttl

if TYPE_CHECKING:
    from celery import Celery

logger = structlog.get_logger("continuous_collector_manager")

# Chaves Redis usadas pelo gerenciador
_AUTOSTART_KEY = "market_alert:continuous_collector:autostart"
_COOLDOWN_KEY = "market_alert:continuous_collector:autostart:cooldown"
_TASK_NAME = "market_alert.tasks.continuous_collector_task.run_continuous_collector"
_MONITOR_QUEUE = "monitor"

# Referência ao monotonic de início do processo, injetada por `celery_app.py`
_process_start_monotonic: float = time.monotonic()


def set_process_start_monotonic(value: float) -> None:
    """ Permite que ``celery_app.py`` injete o timestamp de início do processo. """
    global _process_start_monotonic
    _process_start_monotonic = value


def _get_process_uptime_seconds() -> float:
    return round(time.monotonic() - _process_start_monotonic, 2)


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
