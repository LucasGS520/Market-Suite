""" Políticas de retry centralizadas para tasks Celery do market_alert.

Este módulo consolida dois tipos de retry em um único lugar:

**1. Políticas de task** (dicts para desempacotar nos decorators):

    @celery_app.task(bind=True, name="...", **COLLECTION_RETRY)
    def my_task(self, ...): ...

**2. Lógica de decisão de retry** (classe com regras de negócio):

    should_retry, delay = RetryPolicy.should_retry_lock_failure(attempt=2)
    if should_retry:
        self.retry(countdown=delay)

Responsabilidade única:
    Definir limites, calcular delays e responder perguntas sobre quando
    e por quanto tempo retentar. Não acessa Redis, DB ou Celery diretamente.

Duas políticas de decisão distintas:

    **Lock retry** — quando o lock Redis de um produto está ocupado:
        - Máximo de tentativas: LOCK_RETRY_MAX_RETRIES (3)
        - Backoff exponencial com jitter

    **Scrape retry** — quando o scraping falha temporariamente:
        - Máximo de tentativas: SCRAPE_RETRY_MAX_ATTEMPTS (5)
        - Backoff com respeito ao ``Retry-After`` do servidor
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_alert.infraestructure.resilience.rate_limiter import _compute_lock_retry_delay, _compute_scrape_retry_delay


# ---------------------------------------------------------------------------
# Constantes de política de lock/scrape — ponto único de verdade
# ---------------------------------------------------------------------------

#: Máximo de retentativas ao falhar em adquirir o lock Redis
LOCK_RETRY_MAX_RETRIES: int = 3

#: Delay máximo para lock retry (em segundos)
LOCK_RETRY_MAX_DELAY_SECONDS: int = 30

#: Máximo de retentativas para falhas temporárias de scraping
SCRAPE_RETRY_MAX_ATTEMPTS: int = 5

#: Janela de tempo para contar tentativas de scraping (em segundos)
SCRAPE_RETRY_WINDOW_SECONDS: int = 15 * 60  # 15 minutos

#: TTL do contador de retentativas de scraping no Redis
SCRAPE_RETRY_TTL_SECONDS: int = 60 * 60  # 1 hora

#: Motivos que indicam cooldown obrigatório (ex.: rate limit do servidor)
COOLDOWN_REASONS: frozenset[str] = frozenset({"rate_limit", "429", "temporary_failure"})


# ---------------------------------------------------------------------------
# Políticas de task por domínio (dicts para desempacotar nos decorators)
# ---------------------------------------------------------------------------

#: Coleta de produto monitorado ou concorrente.
#: Retry apenas para lock_skipped — scrape retries são gerenciados pela política
#: de backoff interna (RetryPolicy.should_retry_scrape_failure).
COLLECTION_RETRY: dict = {
    "max_retries": LOCK_RETRY_MAX_RETRIES,
    "soft_time_limit": 90,
    "time_limit": 120,
    "acks_late": True,
}

#: Comparação de preços. Falha rápida sem retry — o próximo ciclo de coleta
#: aciona nova comparação automaticamente.
#:
#: Nota operacional:
#: ``max_retries=0`` é intencional para evitar backlog em picos e preservar
#: a fila de comparação como "best effort" orientada ao ciclo contínuo.
#: Só aumente esse valor quando houver evidência de falhas transitórias
#: frequentes; ao alterar, monitore crescimento de fila/DLQ e latência.
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

#: Verificação de email e SMS. Até 3 tentativas com backoff de 30s.
VERIFICATION_RETRY: dict = {
    "max_retries": 3,
    "default_retry_delay": 30,
    "soft_time_limit": 30,
    "time_limit": 60,
}

def _notification_retry() -> dict:
    """ Retorna política de notificação com max_retries baseado em settings. """
    from market_alert.core.config_alert import settings
    return {
        "max_retries": settings.NOTIFICATION_MAX_ATTEMPTS,
        "soft_time_limit": 30,
        "time_limit": 60,
        "acks_late": True,
    }

NOTIFICATION_RETRY: dict = _notification_retry()


# ---------------------------------------------------------------------------
# Classe de decisão de retry (lógica de quando/quanto retentar)
# ---------------------------------------------------------------------------

class RetryPolicy:
    """ Consolida todas as decisões de retry para coletas de produtos.

    Todos os métodos são estáticos — não há estado interno. Chame diretamente
    via ``RetryPolicy.should_retry_lock_failure(attempt)`` sem instanciar.

    Exemplo::

        should_retry, delay = RetryPolicy.should_retry_lock_failure(attempt=2)
        if should_retry:
            self.retry(countdown=delay)
    """

    @staticmethod
    def should_retry_lock_failure(
        attempt: int,
        max_attempts: int = LOCK_RETRY_MAX_RETRIES,
    ) -> tuple[bool, float]:
        """ Decide se deve retentar após falha em adquirir o lock Redis.

        Args:
            attempt: número da tentativa atual (começa em 1).
            max_attempts: número máximo de tentativas permitidas.

        Returns:
            (deve_retry: bool, delay_seconds: float)
        """
        if max_attempts <= 0:
            return False, 0.0
        
        sanitized_attempt = max(1, attempt)
        if sanitized_attempt > max_attempts:
            return False, 0.0
        
        delay = RetryPolicy.compute_lock_retry_delay(sanitized_attempt)
        return True, float(delay)

    @staticmethod
    def should_retry_scrape_failure(
        reason: str,
        attempt: int,
        retry_after: int | None = None,
        max_seconds: int | None = None,
        max_attempts: int = SCRAPE_RETRY_MAX_ATTEMPTS,
        now: datetime | None = None,
    ) -> tuple[bool, datetime | None]:
        """ Decide se deve retentar falhas de scraping e calcula o próximo check.

        Args:
            reason: motivo da falha (ex.: 'rate_limit', 'timeout').
            attempt: número da tentativa atual.
            retry_after: valor ``Retry-After`` retornado pelo servidor.
            max_seconds: limite máximo de delay permitido.
            max_attempts: número máximo de tentativas permitidas.
            now: referência temporal injetável para testes determinísticos.

        Returns:
            (deve_retry: bool, next_check_at: datetime | None)
        """
        if max_attempts <= 0:
            return False, None

        sanitized_attempt = max(1, attempt)
        if sanitized_attempt > max_attempts:
            return False, None

        delay = RetryPolicy.compute_scrape_retry_delay(
            reason,
            sanitized_attempt,
            retry_after=retry_after,
            max_seconds=max_seconds,
        )
        reference_now = now or datetime.now(timezone.utc)
        next_check_at = reference_now + timedelta(seconds=delay)
        return True, next_check_at

    @staticmethod
    def compute_lock_retry_delay(attempt: int) -> float:
        """ Calcula delay de lock retry com backoff exponencial e jitter. """
        raw = _compute_lock_retry_delay(
            attempt,
            max_seconds=LOCK_RETRY_MAX_DELAY_SECONDS,
        )
        return float(raw)

    @staticmethod
    def compute_scrape_retry_delay(
        reason: str,
        attempt: int,
        *,
        retry_after: int | None = None,
        max_seconds: int | None = None,
    ) -> float:
        """ Calcula delay de scrape retry baseado no motivo e tentativa. """
        sanitized_reason = (reason or "").strip().lower()
        # Motivos críticos de cooldown priorizam Retry-After quando disponível.
        effective_retry_after = retry_after if RetryPolicy.is_cooldown_reason(sanitized_reason) else None
        
        raw = _compute_scrape_retry_delay(
            attempt,
            retry_after=effective_retry_after,
            max_seconds=max_seconds if max_seconds is not None else SCRAPE_RETRY_WINDOW_SECONDS,
        )
        return float(raw)

    @staticmethod
    def is_cooldown_reason(reason: str) -> bool:
        """ Verifica se o motivo exige cooldown obrigatório. """
        return (reason or "").strip().lower() in COOLDOWN_REASONS


__all__ = [
    "RetryPolicy",
    "LOCK_RETRY_MAX_RETRIES",
    "LOCK_RETRY_MAX_DELAY_SECONDS",
    "SCRAPE_RETRY_MAX_ATTEMPTS",
    "SCRAPE_RETRY_WINDOW_SECONDS",
    "SCRAPE_RETRY_TTL_SECONDS",
    "COOLDOWN_REASONS",
    "COLLECTION_RETRY",
    "COMPARISON_RETRY",
    "ENQUEUE_RETRY",
    "NOTIFICATION_RETRY",
    "VERIFICATION_RETRY",
]
