""" Implementações de Circuit Breaker utilizadas pelo ``market_scraper``

O móudulo fornece duas camadas principais:

* :class:`CircuitBreaker` - Implementação básica com armazenamento em Redis.
* :class:`DomainCircuitBreaker` - Fachada que aplica políticas por domínio e centraliza a composição das chaves de monitoramento.

Além disso, um registro global (:data: `domain_circuit_breaker_registry`) é exposto para reutilização ao longo do pipeline de scraping.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Iterable, Optional

import requests

from shared.core.config_base import ConfigBase
from shared import metrics
from shared.utils.redis_client import get_redis_client

from market_scraper.utils_controllers.configuration.circuit_breaker_config import (
    CircuitBreakerPolicy,
    settings as circuit_breaker_settings,
)


_settings = ConfigBase()

@dataclass(frozen=True)
class CircuitBreakerLevels:
    """ Agrupa thresholds e tempos de suspensão configurados
    
    A estrutura facilita a serialização do estado atual e permite compor
    níveis adicionais conforme a política de cada domínio evolui.
    """
    thresholds: tuple[tuple[int, int], ...]
    
    def as_list(self) -> list[tuple[int, int]]:
        """ Retorna representação mutável apropriada para o ``CircuitBreaker`` base """
        return list(self.thresholds)

class CircuitBreaker:
    """ Circuit Breaker com múltiplos níveis de severidade armazenados em Redis """

    def __init__(
        self,
        redis=None,
        levels: Optional[Iterable[tuple[int, int]]] = None,
        webhook: str | None = None,
    ) -> None:
        """ Inicializa o Circuit Breaker

        Parâmetros
        ----------
        redis:
            Instância de Redis utilizada para armazenar o estado do circuito.
            Quando ``None`` é informado, um cliente padrão é obtido via
            :func:`shared.utils.redis_client.get_redis_client`.
        levels:
            Coleção de tuplas ``(limite_de_falhas, tempo_de_suspensao)``. Caso
            não seja informado, os valores padrão definido em 
            :class:`shared.core.config_base.ConfigBase` são utilizados.
        webhook:
            URL opcional para envio de notificações quando o último nível
            de severidade é atingido.
        """
        self.redis = redis or get_redis_client()
        self._lock = threading.Lock()

        if levels is not None:
            self.levels = list(levels)
        else:
            self.levels = [
                (_settings.CIRCUIT_LVL1_THRESHOLD, _settings.CIRCUIT_LVL1_SUSPEND),
                (_settings.CIRCUIT_LVL2_THRESHOLD, _settings.CIRCUIT_LVL2_SUSPEND),
                (_settings.CIRCUIT_LVL3_THRESHOLD, _settings.CIRCUIT_LVL3_SUSPEND),
            ]

        self.webhook = webhook or _settings.SLACK_WEBHOOK_URL

    # ---------- MÉTODOS UTILITÁRIOS INTERNOS ----------
    def _get_keys(self, key: str) -> tuple[str, str]:
        """ Retorna o par de chaves auxiliares utilizadas no Redis """
        return f"{key}:failures", f"{key}:suspend"
    
    def configure_levels(self, levels: Iterable[tuple[int, int]]) -> None:
        """ Atualiza dinamicamente os níveis de severidade
        
        O método não reinicia contadores existentes, apenas define os novos
        thresholds que serão considerados a partir do próximo ``record_failure``.
        """
        with self._lock:
            self.levels = list(levels)

        
    # ---------- OPERAÇÕES PÚBLICAS ----------
    def allow_request(self, key: str) -> bool:
        """ Retorna ``True`` se o circuito estiver fechado 
        
        Quando a chave de suspensão existir no Redis significa que 
        o circuito está aberto para a chave informada.
        """
        _, suspend_key = self._get_keys(key)
        return not self.redis.exists(suspend_key)

    def record_failure(self, key: str) -> None:
        """ Registra uma falha e abre o circuito de acordo com os níveis atuais """
        with self._lock:
            failures_key, suspend_key = self._get_keys(key)

            #Incrementa falhas e garante expiração após o período de suspensão
            count = self.redis.incr(failures_key)

            #Na primeira falha, ajusta o TTL do contador para recover timeout
            if count == 1:
                max_suspend = max(duration for _, duration in self.levels)
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
        """ Fecha o circuito, limpando contadores e flags de suspensão """
        with self._lock:
            failures_key, suspend_key = self._get_keys(key)
            self.redis.delete(failures_key)
            self.redis.delete(suspend_key)

            metrics.SCRAPER_CIRCUIT_OPEN.labels(state="open").set(0)
            metrics.SCRAPER_CIRCUIT_OPEN.labels(state="closed").set(1)
            metrics.SCRAPER_CIRCUIT_STATE_CHANGES_TOTAL.labels(state="closed").inc()

    # ---------- NOTIFICAÇÕES EXTERNAS ----------
    def _notify_slack(self, threshold: int, suspend_secs: int) -> None:
        """ Envia notificação simples ao Slack via webhook configurado """
        payload = {
            "text": (
                "rotating_light: *Circuit Breaker* Level 3 acionado!\n"
                f"Threshold: {threshold} Falhas atingidas.\n"
                f"Suspensão: {suspend_secs // 60} min."
            )
        }
        try:
            requests.post(
                self.webhook, 
                data=json.dumps(payload), 
                headers={"Content-Type": "application/json"}, 
                timeout=5,
            )
        except Exception:
            #Qualquer falha de notificação não deve interremper o fluxo
            pass

def _levels_from_policy(policy: CircuitBreakerPolicy) -> CircuitBreakerLevels:
    """ Gera níveis progressivos a partir da política por domínio 
    
    A estrutura criada possui três níveis planejados apenas como preparação
    para evoluções futuras do circuito. Atualmente todos se baseiam no 
    ``failure_thrshold`` e ``recovery_time`` definidos no YAML.
    """
    base_threshold = max(1, policy.failure_threshold)
    base_suspend = max(60, policy.recovery_time)

    level_two_threshold = base_threshold + max(1, base_threshold // 2)
    level_three_threshold = level_two_threshold + max(1, base_threshold // 2)

    threshold = (
        (base_threshold, base_suspend),
        (level_two_threshold, base_suspend * 2),
        (level_three_threshold, base_suspend * 4),
    )
    return CircuitBreakerLevels(thresholds=threshold)

class DomainCircuitBreaker:
    """ Fachada que aplica políticas específicas por domínio 
    
    O objetivo é garantir isolamento entre marketplaces, permitindo ajustes
    independentes de limites sem replicar lógica de Redis em diversos pontos
    do código. A composição da chave baseia-se no domínio e aceita um
    sufixo opcional para representar contextos mais granulares.
    """
    def __init__(self, host: str, policy: CircuitBreakerPolicy, *, redis=None) -> None:
        self.host = host or "default"
        self.policy = policy
        self._breaker = CircuitBreaker(
            redis=redis,
            levels=_levels_from_policy(policy).as_list(),
        )
        self._lock = threading.Lock()

    # ---------- NORMALIZAÇÃO DAS CHAVES ----------
    def _compose_key(self, key: str | None) -> str:
        """ Constrói a chave combinando domínio e identificador opcional """
        if key:
            return f"{self.host}:{key}"
        return self.host

    # ---------- INTERFACE PÚBLICA ----------
    def allow_request(self, key: str | None = None) -> bool:
        """ Verifica se novas requisições são permitidas para o domínio """
        return self._breaker.allow_request(self._compose_key(key))
    
    def record_failure(self, key: str | None = None) -> None:
        """ Registra falha associada ao domínio/identificador informado """
        self._breaker.record_failure(self._compose_key(key))

    def record_success(self, key: str | None = None) -> None:
        """ Limpa o estado do circuito associado ao domínio informado """
        self._breaker.record_success(self._compose_key(key))

    def update_policy(self, policy: CircuitBreakerPolicy) -> None:
        """ Atualiza níveis internos quando uma nova política é carregada """
        with self._lock:
            self.policy = policy
            self._breaker.configure_levels(_levels_from_policy(policy).as_list())

class CircuitBreakerRegistry:
    """ Gerencia instâncias de :class:`DomainCircuitBreaker` por domínio """
    def __init__(self) -> None:
        self.breakers: dict[str, DomainCircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, host: str | None) -> DomainCircuitBreaker:
        """ Retorna o circuito configurado para domínio informado """
        normalized = host.lower() if host else "default"
        policy = circuit_breaker_settings.policy_for(host)

        with self._lock:
            breaker = self._breakers.get(normalized)
            if breaker is None:
                breaker = DomainCircuitBreaker(normalized, policy)
                self._breakers[normalized] = breaker
                return breaker
            
            if breaker.policy.fingerprint() != policy.fingerprint():
                breaker.update_policy(policy)
            return breaker
        
#Instância compartilhada utilizada pelo serviço de scraping
domain_circuit_breaker_registry = CircuitBreakerRegistry()

__all__ = [
    "CircuitBreaker",
    "DomainCircuitBreaker",
    "CircuitBreakerRegistry",
    "domain_circuit_breaker_registry",
]
