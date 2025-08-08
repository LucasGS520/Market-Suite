""" Implementa controle de velocidade e backoff para o scraping """

import time
import random
import threading
from typing import Optional

import alert_app.metrics as metrics

from fastapi import HTTPException, status

from utils.circuit_breaker import CircuitBreaker
from utils.rate_limiter import RateLimiter


class ThrottleManager:
    """ Gerencia um token bucket com jitter, Exponential backoff, integração com circuit breaker e global rate limiter """
    def __init__(self, rate: float, capacity: float, jitter_range: tuple[float, float] = (0.0, 0.0),
                 circuit_breaker: Optional[CircuitBreaker] = None, rate_limiter: Optional[RateLimiter] = None, min_rate: float = 0.01, decrease_factor: float = 0.9):
        #Taxa de refill (tokens por segundo) e capacidade máxima
        self.rate = rate
        self.capacity = capacity

        #Começa com bucket cheio
        self.tokens = capacity

        #Valores mínimos e máximos para jitter
        self.jitter_min, self.jitter_max = jitter_range

        #Timestamp da última atualização so bucket
        self.timestamp = time.monotonic()

        #Lock para garantir thread-safety
        self.lock = threading.Lock()

        #Se não fornecido, cria uma instância própria de circuit breaker
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

        #Sliding-window global rate limiter
        self.rate_limiter = rate_limiter

        #Parâmetros para backoff adaptativo
        self.min_rate = min_rate
        self.decrease_factor = decrease_factor

    def wait(self, circuit_key: str, identifier: Optional[str] = None):
        """ Aguarda token bucket + aplica jitter, verifica global rate limiter se configurado """
        if self.rate_limiter and not self.rate_limiter.allow_request(identifier):
            self.circuit_breaker.record_failure(circuit_key)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

        with self.lock:
            now = time.monotonic()
            elapsed = now - self.timestamp

            #Recarrega tokens proporcional ao tempo decorrido
            refill = elapsed * self.rate
            self.tokens = min(self.capacity, self.tokens + refill)
            self.timestamp = now

            #Se não houver tokens suficientes, aguarde até gerar 1 token
            if self.tokens < 1.0:
                sleep_time = (1.0 - self.tokens) / self.rate

                #Adiciona jitter extra
                jitter = random.uniform(self.jitter_min, self.jitter_max)
                metrics.SCRAPER_JITTER_SECONDS.observe(jitter)
                total_sleep_time = sleep_time + jitter
                time.sleep(total_sleep_time)

                #Após esperar, consome 1 token
                self.tokens = 0.0

            else:
                #Já há token: consome imediatamente, mas ainda aplica jitter
                jitter = random.uniform(self.jitter_min, self.jitter_max)
                metrics.SCRAPER_JITTER_SECONDS.observe(jitter)
                time.sleep(jitter)
                self.tokens -= 1.0

    def backoff(self, attempt: int, circuit_key: str):
        """ Exponential backoff + adaptative rate adjust, chamado quando recebe HTTP 429 """
        #Base random para variar o backoff
        base = random.uniform(self.jitter_min, self.jitter_max)
        delay = (2 ** attempt) * base
        metrics.SCRAPER_JITTER_SECONDS.observe(base)
        time.sleep(delay)

        new_rate = max(self.min_rate, self.rate * self.decrease_factor)
        if new_rate < self.rate:
            self.rate = new_rate
        metrics.SCRAPER_BACKOFF_FACTOR.set(self.rate)

        #Registra falha no circuit breaker
        self.circuit_breaker.record_failure(circuit_key)
