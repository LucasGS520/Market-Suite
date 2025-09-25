""" Gerenciador unificado de ritmo para o fluxo de scraping """

from __future__ import annotations

import asyncio
import random
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import HTTPException, status

from shared.metrics.metrics_scraper import (
    SCRAPER_BACKOFF_FACTOR,
    SCRAPER_HTTP_BLOCKED_TOTAL,
    SCRAPER_JITTER_SECONDS,
)

from market_scraper.utils.circuit_breaker import CircuitBreaker
from market_scraper.utils.config.pace_control import (
    PaceControlPolicy, 
    settings as pace_control_settings
)
from market_scraper.utils.humanized_delay import HumanizedDelayManager
from market_scraper.utils.rate_limiter import RateLimiter


@dataclass
class PaceControlSnapshot:
    """ Representa estado observável do controlador para debug e métricas """
    tokens: float
    rate: float
    capacity: float
    jitter_range: tuple[float, float]

class DomainPaceController:
    """ Controla rate limit, token bucket e delays humanizados por domínio """
    def __init__(self, host: str, policy: PaceControlPolicy) -> None:
        self.host = host or "default"
        self._policy = policy

        self._token_rate = policy.token_bucket.rate
        self._token_capacity = policy.token_bucket.capacity
        self._min_rate = policy.token_bucket.min_rate
        self._decrease_factor = policy.token_bucket.decrease_factor
        self._jitter_min = policy.jitter.min_seconds
        self._jitter_max = policy.jitter.max_seconds

        self._lock = threading.Lock()
        self._tokens = self._token_capacity
        self._timestamp = time.monotonic()

        self.delay_manager = HumanizedDelayManager(
            avg_wpm=policy.human_delay.avg_wpm,
            base_delay=policy.human_delay.base_delay,
            fatigue_range=(policy.human_delay.fatigue_min, policy.human_delay.fatigue_max),
        )

        self.circuit_breaker = CircuitBreaker()
        self.circuit_breaker_config = policy.circuit_breaker

        self.rate_limiter: RateLimiter | None = None
        if policy.rate_limit:
            self.rate_limiter = RateLimiter(
                redis_key=f"scraper:pace:{self.host}",
                max_requests=policy.rate_limit.max_requests,
                window_seconds=policy.rate_limit.window,
            )

    def snapshot(self) -> PaceControlSnapshot:
        """ Retorna fotografia do estado interno para logs e diagnósticos """
        with self._lock:
            return PaceControlSnapshot(
                tokens=self._tokens,
                rate=self._token_rate,
                capacity=self._token_capacity,
                jitter_range=(self._jitter_min, self._jitter_max),
            )
    
    async def wait_for_turn(
        self,
        *,
        circuit_key: str, 
        identifier: Optional[str] = None,
        humanized_text: str | None = None,
        reflection_time: float = 1.0,
    ) -> None:
        """ Aguarda liberação de token, aplica jitter e atraso humanizado """
        if self.rate_limiter and not self.rate_limiter.allow_request(identifier):
            SCRAPER_HTTP_BLOCKED_TOTAL.inc()
            self.circuit_breaker.record_failure(circuit_key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Limite de requisições excedido para o domínio"
            )

        sleep_time = 0.0
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._timestamp
            refill = elapsed * self._token_rate
            self._tokens = min(self._token_capacity, self._tokens + refill)
            self._timestamp = now

            if self._tokens < 1.0:
                deficit = 1.0 - self._tokens
                sleep_time = deficit / max(self._token_rate, 0.001)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0

            jitter = random.uniform(self._jitter_min, self._jitter_max)
            SCRAPER_JITTER_SECONDS.observe(jitter)
            sleep_time += jitter

        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

        if humanized_text is not None:
            await self.delay_manager.wait_async(humanized_text, reflection_time)

    async def backoff(self, *, attempt: int, circuit_key: str) -> None:
        """ Executa backoff exponencial reduzindo gradualmente a taxa """
        base = random.uniform(self._jitter_min, self._jitter_max)
        SCRAPER_JITTER_SECONDS.observe(base)
        await asyncio.sleep((2 ** attempt) * base)

        with self._lock:
            new_rate = max(self._min_rate, self._token_rate * self._decrease_factor)
            if new_rate < self._token_rate:
                self._token_rate = new_rate
            SCRAPER_BACKOFF_FACTOR.set(self._token_rate)

        self.circuit_breaker.record_failure(circuit_key)

    def reset_rate(self) -> None:
        """ Restaura a taxa original após período de estabilidade """
        with self._lock:
            self._token_rate = self.policy.token_bucket.rate

    def update_policy(self, policy: PaceControlPolicy) -> None:
        """ Atualiza parâmetros dinamicamente quando a política muda """
        with self._lock:
            self.policy = policy
            self._token_capacity = policy.token_bucket.capacity
            self._token_rate = policy.token_bucket.rate
            self._min_rate = policy.token_bucket.min_rate
            self._decrease_factor = policy.token_bucket.decrease_factor
            self._jitter_min = policy.jitter.min
            self._jitter_max = policy.jitter.max
            self.delay_manager = HumanizedDelayManager(
                avg_wpm=policy.human_delay.avg_wpm,
                base_delay=policy.human_delay.base_delay,
                fatigue_range=(policy.human_delay.fatigue_min, policy.human_delay.fatigue_max),
            )
            self.circuit_breaker_config = policy.circuit_breaker
            self._tokens = min(self._tokens, self._token_capacity)
            self._timestamp = time.monotonic()

        if policy.rate_limit:
            self.rate_limiter = RateLimiter(
                redis_key=f"scraper:pace:{self.host}",
                max_requests=policy.rate_limit.max_requests,
                window_seconds=policy.rate_limit.window,
            )
        else:
            self.rate_limiter = None

class PaceControllerRegistry:
    """ Gerencia instâncias de ``DomainPaceController`` por domínio """
    def __init__(self):
        self._controllers: Dict[str, DomainPaceController] = {}
        self._lock = threading.Lock()

    def get(self, host: str | None) -> DomainPaceController:
        """ Retorna controlador correspondente ao host, criando se necessário """
        normalized = host.lower() if host else "default"
        policy = pace_control_settings.policy_for(host)

        with self._lock:
            controller = self._controllers.get(normalized)
            if controller is None:
                controller = DomainPaceController(normalized, policy)
                self._controllers[normalized] = controller
                return controller
            
            if controller.policy.fingerprint() != policy.fingerprint():
                controller.update_policy(policy)
            return controller

#Registro compartilhado utilizado pelos serviçoes de scraper        
pace_controller_registry = PaceControllerRegistry()
