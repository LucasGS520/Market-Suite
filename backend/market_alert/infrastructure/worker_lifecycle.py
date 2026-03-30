""" Hooks de lifecycle do worker Celery.

Ponto de extensão para registrar sinais Celery (worker_ready, worker_shutdown, etc.).
O Temporal Worker é iniciado exclusivamente pelo container `market_orchestrator`
dedicado no docker-compose — não há thread daemon aqui.
"""

from __future__ import annotations

import structlog
from celery import Celery
from celery.signals import worker_ready


logger = structlog.get_logger("worker_lifecycle")

def register_worker_signals(celery_app: Celery, process_start_monotonic: float) -> None:
    """Registra sinais do worker Celery.

    Ponto central para adicionar hooks de startup/shutdown do processo Celery.
    O Temporal Worker não é iniciado aqui — roda no container dedicado `market_orchestrator`.

    A validação de infraestrutura (PostgreSQL, Redis, Temporal) é registrada no
    sinal ``worker_ready`` para garantir falha rápida quando o worker efetivamente
    inicia — não em tempo de importação, o que causaria efeito colateral no Uvicorn.
    """
    @worker_ready.connect
    def _validate_on_worker_ready(sender, **kwargs) -> None:
        """Valida infraestrutura assim que o worker está pronto para aceitar tasks."""
        from market_alert.infrastructure.startup_validation import validate_startup_dependencies
        validate_startup_dependencies(strict=True)

    logger.info("worker_lifecycle_registered")
