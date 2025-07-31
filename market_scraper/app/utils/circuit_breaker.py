""" Implementação simples de circuit breaker usando Redis """

import json
import threading

import app.metrics as metrics
from app.utils.redis_client import get_redis_client
from app.core.config import settings
import requests


class CircuitBreaker:
    """ Circuit Breaker com três níveis de severidade, usando Redis """
    _lock = threading.Lock()

    def __init__(self, redis=None, levels=None, webhook=None):
        """ Inicializa o Circuit Breaker

        Parameters
        ----------
        redis: Redis | None
            Instância do Redis utilizada para armazenar o estado.
        levels: list[tuple[int, int]] | None
            Lista de tuplas ``(limite_de_falhas, tempo_de_suspensao)``.
            Caso ``None``, serão utilizados os valores definidos em ```settings``.
        webhook: str | None
            URL para envio de notificação ao Slack quando o nível máximo é atingido.
        """
        self.redis = redis or get_redis_client()

        #Utiliza níveis customizados se forem informados
        if levels is not None:
            self.levels = levels
        else:
            self.levels = [
                (settings.CIRCUIT_LVL1_THRESHOLD, settings.CIRCUIT_LVL1_SUSPEND),
                (settings.CIRCUIT_LVL2_THRESHOLD, settings.CIRCUIT_LVL2_SUSPEND),
                (settings.CIRCUIT_LVL3_THRESHOLD, settings.CIRCUIT_LVL3_SUSPEND)
            ]

        self.webhook = webhook or settings.SLACK_WEBHOOK_URL

    def _gets_keys(self, key: str):
        return f"{key}:failures", f"{key}:suspend"

    def allow_request(self, key: str) -> bool:
        """ Retorna True se o circuito estiver fechado (permitindo requisições), ou False se estiver aberto/suspenso """
        _, suspend_key = self._gets_keys(key)
        return not self.redis.exists(suspend_key)

    def record_failure(self, key: str) -> None:
        """ Incrementa contador de falhas. Se atingir o limite, abre o circuito (seta suspend_key com TTL)"""
        with self._lock:
            failures_key, suspend_key = self._gets_keys(key)

            #Incrementa falhas e garante que expire após o período de suspensão
            count = self.redis.incr(failures_key)

            #Na primeira falha, ajusta o TTL do contador para recover timeout
            if count == 1:
                max_suspend = max(d for _, d in self.levels)
                self.redis.expire(failures_key, max_suspend)

            #Identifica o maior nível de suspensão correspondente
            for idx, (threshold, suspend_secs) in reversed(list(enumerate(self.levels))):
                if count >= threshold:
                    #No nível mais alto, mantém o tempo do nível anterior
                    if idx == len(self.levels) - 1 and idx > 0:
                        suspend_secs = self.levels[idx - 1][1]

                    self.redis.set(suspend_key, "1", ex=suspend_secs)

                    metrics.SCRAPER_CIRCUIT_OPEN.labels(state="open").set(1)
                    metrics.SCRAPER_CIRCUIT_OPEN.labels(state="closed").set(0)
                    metrics.SCRAPER_CIRCUIT_STATE_CHANGES_TOTAL.labels(state="open").inc()

                    #Notificar apenas no level 3
                    if idx == len(self.levels) - 1 and self.webhook:
                        self._notify_slack(threshold, suspend_secs)
                    break

    def record_success(self, key: str) -> None:
        """ Fecha o circuito, limpando flags e contadores """
        with self._lock:
            failures_key, suspend_key = self._gets_keys(key)
            self.redis.delete(failures_key)
            self.redis.delete(suspend_key)

            metrics.SCRAPER_CIRCUIT_OPEN.labels(state="open").set(0)
            metrics.SCRAPER_CIRCUIT_OPEN.labels(state="closed").set(1)
            metrics.SCRAPER_CIRCUIT_STATE_CHANGES_TOTAL.labels(state="closed").inc()

    def _notify_slack(self, threshold: int, suspend_secs: int) -> None:
        """ Envia notificação simples ao Slack via webhook configurado """
        payload = {
            "text": (
                f"rotating_light: *Circuit Breaker* Level 3 acionado!\n"
                f"Threshold: {threshold} Falhas atingidas.\n"
                f"Suspensão: {suspend_secs//60} min."
            )
        }
        try:
            requests.post(self.webhook, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=5)
        except Exception:
            pass
