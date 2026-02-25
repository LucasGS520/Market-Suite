""" Políticas de retry nomeadas para tasks Celery do market_alert.

Centraliza max_retries, soft_time_limit e time_limit em um único lugar,
eliminando constantes espalhadas nos decorators. Cada política é um dict
que pode ser desempacotado diretamente no decorator da task::

    @celery_app.task(bind=True, name="...", queue="...", **COLLECTION_RETRY)
    def my_task(self, ...):
        ...

Adicionar uma nova policy aqui é suficiente — não é necessário editar
cada task individualmente para ajustar timeouts ou tentativas.
"""

from __future__ import annotations

from market_alert.orchestrator.retry_policy import LOCK_RETRY_MAX_RETRIES

# ---------------------------------------------------------------------------
# Políticas por domínio
# ---------------------------------------------------------------------------

#: Coleta de produto monitorado ou concorrente.
#: Retry apenas para lock_skipped — scrape retries são gerenciados pela policy
#: de backoff interna (RetryPolicy.should_retry_scrape_failure).
COLLECTION_RETRY: dict = {
    "max_retries": LOCK_RETRY_MAX_RETRIES,
    "soft_time_limit": 90,
    "time_limit": 120,
    "acks_late": True,
}

#: Comparação de preços. Falha rápida sem retry — o próximo ciclo de coleta
#: aciona nova comparação automaticamente.
COMPARISON_RETRY: dict = {
    "max_retries": 0,
    "soft_time_limit": 20,
    "time_limit": 40,
    "acks_late": True,
}

#: Enfileiramento de notificações pendentes. Idempotente — não há benefício
#: em retentar, pois o próximo beat schedule reprocessa os pendentes.
ENQUEUE_RETRY: dict = {
    "max_retries": 0,
    "soft_time_limit": 20,
    "time_limit": 40,
    "acks_late": True,
}

#: Envio de notificação individual. Usa settings.NOTIFICATION_MAX_ATTEMPTS
#: para respeitar o limite configurável sem hardcode na task.
def _notification_retry() -> dict:
    """ Retorna policy de notificação com max_retries baseado em settings. """
    from market_alert.core.config_alert import settings
    return {
        "max_retries": settings.NOTIFICATION_MAX_ATTEMPTS,
        "soft_time_limit": 30,
        "time_limit": 60,
        "acks_late": True,
    }


NOTIFICATION_RETRY: dict = _notification_retry()

#: Verificação de email e SMS. Até 3 tentativas com backoff de 30s.
VERIFICATION_RETRY: dict = {
    "max_retries": 3,
    "default_retry_delay": 30,
    "soft_time_limit": 30,
    "time_limit": 60,
}


__all__ = [
    "COLLECTION_RETRY",
    "COMPARISON_RETRY",
    "ENQUEUE_RETRY",
    "NOTIFICATION_RETRY",
    "VERIFICATION_RETRY",
]
