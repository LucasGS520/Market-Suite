""" Gerencia hooks de lifecycle do worker Celery.

Centraliza os sinais ``worker_ready`` e similares em um único lugar,
mantendo ``celery_app.py`` livre de lógica operacional.

Responsabilidade única:
    Registrar handlers para eventos do worker (startup, shutdown, etc.)
    e delegar para serviços especializados. Nenhuma lógica de negócio aqui.

Uso::

    from market_alert.infra.worker_lifecycle import register_worker_signals
    register_worker_signals(celery_app, process_start_monotonic)
"""

from __future__ import annotations

import structlog
from celery import Celery
from celery.signals import worker_ready


logger = structlog.get_logger("worker_lifecycle")

def register_worker_signals(celery_app: Celery, process_start_monotonic: float) -> None:
    """ Registra os sinais de lifecycle do worker.

    Deve ser chamada após a criação da instância ``celery_app``, antes de
    qualquer worker ser iniciado. Em testes que não iniciam workers, esta
    função pode ser ignorada sem efeitos colaterais.

    Args:
        celery_app: Instância da aplicação Celery.
        process_start_monotonic: Timestamp monotônico de início do processo
            (``time.monotonic()`` capturado no startup), usado para calcular
            uptime e cooldowns de revalidação.
    """

    @worker_ready.connect
    def _on_worker_ready(**kwargs):
        """ Inicia rotinas de suporte assim que o worker estiver pronto.

        Delega inteiramente para ``continuous_collector_manager``, mantendo
        este arquivo livre de detalhes de coleta.
        """
        from market_alert.collectors.services.continuous_collector_manager import (
            request_start,
            set_process_start_monotonic,
            start_revalidation_loop,
        )
        logger.info("worker_ready_signal_received")
        set_process_start_monotonic(process_start_monotonic)
        request_start(celery_app)
        start_revalidation_loop(celery_app)
