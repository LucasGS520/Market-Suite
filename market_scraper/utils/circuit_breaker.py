""" Implementações de Circuit Breaker utilizadas pelo ``market_scraper``

O módulo fornece duas camadas principais:

* :class:`CircuitBreaker` - Implementação básica com armazenamento em Redis.
* :class:`DomainCircuitBreaker` - Fachada que aplica políticas por domínio e centraliza a composição das chaves de monitoramento.

Além disso, um registro global (:data: `domain_circuit_breaker_registry`) é exposto 
para reutilização ao longo do pipeline de scraping.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Iterable, Optional

import requests
import structlog

from shared.core.config_base import ConfigBase
from shared.metrics import metrics_scraper as metrics
from shared.utils.logging_utils import sanitize_log_data
from shared.utils.redis_client import get_redis_client

from market_scraper.utils_controllers.configuration.circuit_breaker_config import (
    CircuitBreakerPolicy,
    settings as circuit_breaker_settings,
)


_settings = ConfigBase()
logger = structlog.get_logger("circuit_breaker")

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

@dataclass(frozen=True)
class CircuitBreakerDecision:
    """ Representa o resultado da avaliação após registrar uma falha
    
    Attributes
    ----------
    faliure_count:
        Quantidade total de falhas registradas para a chave analisada
    level:
        Índice (base 1) do nível de severidade atingido. ``None`` indica que
        nenhum limiar foi ultrapassado.
    suspend_seconds:
        Tempo de suspensão aplicado. ``None`` representa ausência de bloqueio.
    opened:
        Indica se o circuito foi aberto nesta avaliação
    """
    failure_count: int
    level: int | None
    suspend_seconds: int | None
    opened: bool

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
            não seja informado, os valores padrão definidos em 
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
        """ Retorna ``True`` quando o circuito está fechado para a chave informada
        
        Caso ocorra alguma falha de comunicação com o Redis o método opta por
        ``fail-open`` (retorna ``True``), preservando a continuidade do serviço.
        """
        _, suspend_key = self._get_keys(key)
        try:
            return not self.redis.exists(suspend_key)
        except Exception as err:
            logger.warning(
                "circuit_allow_failure",
                key=sanitize_log_data(key),
                error=sanitize_log_data(str(err)),
            )
            return True

    def record_failure(self, key: str) -> CircuitBreakerDecision:
        """ Registra uma falha e avalia a necessidade de suspensão """
        with self._lock:
            failures_key, suspend_key = self._get_keys(key)

            try:
                count = self.redis.incr(failures_key)
            except Exception as err:
                logger.warning(
                    "circuit_register_failure_error",
                    key=sanitize_log_data(key),
                    error=sanitize_log_data(str(err)),
                )
                return CircuitBreakerDecision(
                    failure_count=0,
                    level=None,
                    suspend_seconds=None,
                    opened=False,
                )
            
            #Na primeira falha, ajusta o TTL do contador para recover timeout
            if count == 1:
                try:
                    max_suspend = max(duration for _, duration in self.levels)
                except ValueError:
                    max_suspend = _settings.CIRCUIT_LVL1_SUSPEND
                try:
                    self.redis.expire(failures_key, max_suspend)
                except Exception as err:
                    logger.warning(
                        "circuit_expire_failure",
                        key=sanitize_log_data(key),
                        error=sanitize_log_data(str(err)),
                    )

            triggered_level: int | None = None
            suspend_secs: int | None = None

            for idx, (threshold, duration) in reversed(list(enumerate(self.levels))):
                level_index = idx + 1
                if count >= threshold:
                    #No nível mais alto, mantém o tempo do nível anterior
                    triggered_level = level_index
                    suspend_secs = duration
                    if idx == len(self.levels) - 1 and idx > 0:
                        suspend_secs = self.levels[idx - 1][1]
                    try:
                        self.redis.set(suspend_key, "1", ex=suspend_secs)
                    except Exception as err:
                        logger.warning(
                            "circuit_suspend_failure",
                            key=sanitize_log_data(key),
                            error=sanitize_log_data(str(err)),
                        )
                        suspend_secs = None
                        triggered_level = None
                    break
            
            return CircuitBreakerDecision(
                failure_count=count,
                level=triggered_level,
                suspend_seconds=suspend_secs,
                opened=triggered_level is not None and suspend_secs is not None,
            )

    def record_success(self, key: str) -> bool:
        """ Fecha o circuito, limpando contadores e flags de suspensão """
        with self._lock:
            failures_key, suspend_key = self._get_keys(key)
            try:
                removed = self.redis.delete(failures_key, suspend_key)
            except TypeError:
                #Compatibilidade com instâncias Redis que aceitam apenas um argumento
                try:
                    removed = 0
                    removed += self.redis.delete(failures_key)
                    removed += self.redis.delete(suspend_key)
                except Exception as err:
                    logger.warning(
                        "circuit_success_cleanup_failure",
                        key=sanitize_log_data(key),
                        error=sanitize_log_data(str(err)),
                    )
                    return False
            except Exception as err:
                logger.warning(
                    "circuit_success_cleanup_failure",
                    key=sanitize_log_data(key),
                    error=sanitize_log_data(str(err)),
                )
                return False
            
        return bool(removed)

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
    para evoluções futuras do circuito. Atualmente todos se baseiam nos
    atributos ``failure_threshold`` e ``recovery_time`` definidos no YAML.
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

        metrics.SCRAPER_CIRCUIT_STATE.labels(host=self.host, state="open").set(0)
        metrics.SCRAPER_CIRCUIT_STATE.labels(host=self.host, state="closed").set(1)

    # ---------- NORMALIZAÇÃO DAS CHAVES ----------
    def _compose_key(self, key: str | None) -> str:
        """ Constrói a chave combinando domínio e identificador opcional """
        if key:
            return f"{self.host}:{key}"
        return self.host
    
    def _safe_key(self, key: str | None) -> str | None:
        """ Normaliza a chave para logs sem expor dados sensíveis """
        if key is None:
            return None
        return sanitize_log_data(str(key))

    # ---------- INTERFACE PÚBLICA ----------
    def allow_request(self, key: str | None = None) -> bool:
        """ Verifica se novas requisições são permitidas para o domínio """
        composed_key = self._compose_key(key)
        allowed = self._breaker.allow_request(composed_key)

        result = "allowed" if allowed else "blocked"
        metrics.SCRAPER_CIRCUIT_ATTEMPTS_TOTAL.labels(
            host=self.host,
            result=result,
        ).inc()

        if not allowed:
            logger.info(
                "circuit_breaker_request_blocked",
                domain=self.host,
                key=self._safe_key(key),
            )
        
        return allowed
    
    def record_failure(self, key: str | None = None) -> CircuitBreakerDecision:
        """ Registra falha associada ao domínio ou identificador informado """
        composed_key = self._compose_key(key)
        decision = self._breaker.record_failure(composed_key)

        metrics.SCRAPER_CIRCUIT_ATTEMPTS_TOTAL.labels(
            host=self.host,
            result="failure",
        ).inc()

        if decision.opened:
            metrics.SCRAPER_CIRCUIT_STATE.labels(host=self.host, state="open").set(1)
            metrics.SCRAPER_CIRCUIT_STATE.labels(host=self.host, state="closed").set(0)
            metrics.SCRAPER_CIRCUIT_TRANSITIONS_TOTAL.labels(host=self.host, state="open").inc()

            level_label = (
                f"level_{decision.level}" if decision.level is not None else "unknown_level"
            )
            metrics.SCRAPER_CIRCUIT_SUSPENSIONS_TOTAL.labels(
                host=self.host,
                level=level_label,
            ).inc()

            logger.warning(
                "circuit_breaker_opened",
                domain=self.host,
                key=self._safe_key(key),
                failures=decision.failure_count,
                level=decision.level,
                suspend_seconds=decision.suspend_seconds,
            )

            if decision.level == len(self._breaker.levels) and decision.suspend_seconds:
                self._breaker._notify_slack(decision.failure_count, decision.suspend_seconds)

        return decision
    
    def record_success(self, key: str | None = None) -> bool:
        """ Limpa o estado do circuito associado ao domínio informado """
        composed_key = self._compose_key(key)
        closed = self._breaker.record_success(composed_key)

        if closed:
            metrics.SCRAPER_CIRCUIT_STATE.labels(host=self.host, state="open").set(0)
            metrics.SCRAPER_CIRCUIT_STATE.labels(host=self.host, state="closed").set(1)
            metrics.SCRAPER_CIRCUIT_TRANSITIONS_TOTAL.labels(host=self.host, state="closed").inc()
            
            logger.info(
                "circuit_breaker_closed",
                domain=self.host,
                key=self._safe_key(key),
            )
        
        return closed

    def update_policy(self, policy: CircuitBreakerPolicy) -> None:
        """ Atualiza níveis internos quando uma nova política é carregada """
        with self._lock:
            self.policy = policy
            self._breaker.configure_levels(_levels_from_policy(policy).as_list())

class CircuitBreakerRegistry:
    """ Gerencia instâncias de :class:`DomainCircuitBreaker` por domínio """
    def __init__(self) -> None:
        self._breakers: dict[str, DomainCircuitBreaker] = {}
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
    "CircuitBreakerDecision",
    "DomainCircuitBreaker",
    "CircuitBreakerRegistry",
    "domain_circuit_breaker_registry",
]
