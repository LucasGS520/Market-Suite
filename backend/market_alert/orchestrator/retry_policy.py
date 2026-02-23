""" Política centralizada de retry para coletas de produtos.

``RetryPolicy`` consolida todas as decisões de retry em um único lugar,
eliminando constantes espalhadas por múltiplos módulos. Qualquer lógica
de "quando e por quanto tempo tentar novamente" deve passar por aqui.

Responsabilidade única:
    Definir limiares, calcular delays e responder perguntas binárias sobre
    retry (deve/não deve). Não acessa Redis, DB ou Celery diretamente.

Duas políticas distintas:

    **Lock retry** — quando o lock Redis de um produto está ocupado:
        - Máximo de tentativas: LOCK_RETRY_MAX_RETRIES
        - Backoff exponencial com jitter (via rate_limiter)

    **Scrape retry** — quando o scraping falha temporariamente (timeout,
    rate-limit, erro de servidor):
        - Máximo de tentativas: SCRAPE_RETRY_MAX_ATTEMPTS
        - Backoff com respeito ao ``Retry-After`` do servidor
        - Cooldown adicional para erros de rate-limit

Exemplo de uso::

    if RetryPolicy.should_retry_lock_failure(attempt=2):
        delay = RetryPolicy.compute_lock_retry_delay(attempt=2)
        self.retry(countdown=delay)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_alert.utils.rate_limiter import (
    _compute_lock_retry_delay,
    _compute_scrape_retry_delay,
)


# ---------------------------------------------------------------------------
# Constantes de política — ponto único de verdade para todos os limites
# ---------------------------------------------------------------------------

#:Número máximo de retentativas ao falhar em adquirir o lock Redis
LOCK_RETRY_MAX_RETRIES: int = 3

#:Delay máximo para lock retry (em segundos)
LOCK_RETRY_MAX_DELAY_SECONDS: int = 30

#:Número máximo de retentativas para falhas temporárias de scraping
SCRAPE_RETRY_MAX_ATTEMPTS: int = 5

#:Janela de tempo para contar tentativas de scraping (em segundos)
SCRAPE_RETRY_WINDOW_SECONDS: int = 15 * 60  # 15 minutos

#:TTL do contador de retentativas de scraping no Redis
SCRAPE_RETRY_TTL_SECONDS: int = 60 * 60  # 1 hora

#:Motivos que indicam cooldown obrigatório (ex.: rate limit do servidor)
COOLDOWN_REASONS: frozenset[str] = frozenset({"rate_limit", "429", "temporary_failure"})

class RetryPolicy:
    """ Consolida todas as decisões de retry para coletas de produtos.

    Todos os métodos são estáticos — não há estado interno. Chame diretamente
    via ``RetryPolicy.should_retry_lock_failure(attempt)`` sem instanciar.
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
        if attempt > max_attempts:
            return False, 0.0
        delay = RetryPolicy.compute_lock_retry_delay(attempt)
        return True, float(delay)

    @staticmethod
    def should_retry_scrape_failure(
        reason: str,
        attempt: int,
        max_attempts: int = SCRAPE_RETRY_MAX_ATTEMPTS,
    ) -> tuple[bool, datetime | None]:
        """ Decide se deve retentar após falha de scraping.

        Args:
            reason: motivo da falha (ex.: 'rate_limit', 'timeout').
            attempt: número da tentativa atual.
            max_attempts: número máximo de tentativas permitidas.

        Returns:
            (deve_retry: bool, next_check_at: datetime | None)
            ``next_check_at`` é None quando deve_retry é False.
        """
        if attempt > max_attempts:
            return False, None

        delay = RetryPolicy.compute_scrape_retry_delay(reason, attempt)
        next_check_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        return True, next_check_at

    @staticmethod
    def compute_lock_retry_delay(attempt: int) -> float:
        """ Calcula delay de lock retry com backoff exponencial e jitter.

        Args:
            attempt: número da tentativa (começa em 1).

        Returns:
            Delay em segundos (nunca excede LOCK_RETRY_MAX_DELAY_SECONDS).
        """
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
        """ Calcula delay de scrape retry baseado no motivo e tentativa.

        Respeita ``Retry-After`` do servidor quando disponível.

        Args:
            reason: motivo da falha (usado para log; reservado para extensões futuras).
            attempt: número da tentativa atual.
            retry_after: valor ``Retry-After`` do servidor em segundos.
            max_seconds: teto para o delay calculado (padrão: SCRAPE_RETRY_WINDOW_SECONDS).

        Returns:
            Delay em segundos.
        """
        raw = _compute_scrape_retry_delay(
            attempt,
            retry_after=retry_after,
            max_seconds=max_seconds if max_seconds is not None else SCRAPE_RETRY_WINDOW_SECONDS,
        )
        return float(raw)

    @staticmethod
    def is_cooldown_reason(reason: str) -> bool:
        """ Verifica se o motivo exige cooldown obrigatório.

        Args:
            reason: motivo da falha normalizado (ex.: 'rate_limit').

        Returns:
            True se o motivo está na lista de cooldown.
        """
        return (reason or "").strip().lower() in COOLDOWN_REASONS


__all__ = [
    "RetryPolicy",
    "LOCK_RETRY_MAX_RETRIES",
    "LOCK_RETRY_MAX_DELAY_SECONDS",
    "SCRAPE_RETRY_MAX_ATTEMPTS",
    "SCRAPE_RETRY_WINDOW_SECONDS",
    "SCRAPE_RETRY_TTL_SECONDS",
    "COOLDOWN_REASONS",
]
