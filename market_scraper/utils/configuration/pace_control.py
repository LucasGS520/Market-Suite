""" Loader de configuração para o controle de ritmo do scraper """

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import os
import threading

import yaml

from market_scraper.core.config_scraper import settings as scraper_settings


__all__ = [
    "RateLimitConfig",
    "TokenBucketConfig",
    "JitterConfig",
    "HumanDelayConfig",
    "CircuitBreakerConfig",
    "PaceControlPolicy",
    "PaceControlSettings",
    "settings",
]

@dataclass(frozen=True)
class RateLimitConfig:
    """ Configura limites de requisições por janela """
    max_requests: int
    window: int

@dataclass(frozen=True)
class TokenBucketConfig:
    """ Parâmetros para o algoritmo de token bucket utilizado pelo pace control """
    rate: float
    capacity: float
    min_rate: float
    decrease_factor: float

@dataclass(frozen=True)
class JitterConfig:
    """ Faixa de jitter aplicada entre requisições """
    min: float
    max: float

@dataclass(frozen=True)
class HumanDelayConfig:
    """ Configuração de atraso humanizado utilizado para simular navegação """
    avg_wpm: float
    base_delay: float
    fatigue_min: float
    fatigue_max: float

@dataclass(frozen=True)
class CircuitBreakerConfig:
    """ Estrutura base para configuração de circuit breaker por domínio """
    failure_threshold: int
    recovery_time: int

@dataclass(frozen=True)
class PaceControlPolicy:
    """ Agrega todas as configurações necessárias para o controle de ritmo """
    rate_limit: RateLimitConfig | None
    token_bucket: TokenBucketConfig
    jitter: JitterConfig
    human_delay: HumanDelayConfig
    circuit_breaker: CircuitBreakerConfig

    def fingerprint(self) -> tuple:
        """ Retorna assinatura imutável da política para permitir cache seguro """
        rate_tuple = (self.rate_limit.max_requests, self.rate_limit.window)
        if self.rate_limit:
            rate_tuple = (self.rate_limit.max_requests, self.rate_limit.window)
        return (
            rate_tuple,
            self.token_bucket.rate,
            self.token_bucket.capacity,
            self.token_bucket.min_rate,
            self.token_bucket.decrease_factor,
            self.jitter.min,
            self.jitter.max,
            self.human_delay.avg_wpm,
            self.human_delay.base_delay,
            self.human_delay.fatigue_min,
            self.human_delay.fatigue_max,
            self.circuit_breaker.failure_threshold,
            self.circuit_breaker.recovery_timeout,
        )
    
class PaceControlSettings:
    """ Representa o conjunto carregado de políticas de pace control """
    def __init__(self, *, defaults: PaceControlPolicy, domains: Dict[str, PaceControlPolicy]) -> None:
        self._defaults = defaults
        self._domains = domains

    def policy_for(self, host: str | None) -> PaceControlPolicy:
        """ Seleciona a política apropriada para o host informado """
        if not host:
            return self._defaults
        
        host = host.lower()

        for domain, policy in self._domains.items():
            if host == domain or host.endswith("." + domain):
                return policy
            
        return self._defaults
    
def _config_path() -> Path:
    """ Resolve o caminho do arquivo de configuração considerando variáveis de ambiente """
    default = Path(__file__).with_name("pace_control.yaml")
    raw_path = os.getenv("PACE_CONTROL_CONFIG_FILE")
    if raw_path:
        return Path(raw_path)
    return default

_CONFIG_LOCK = threading.Lock()
_CACHED_SETTINGS: PaceControlSettings | None = None
_CACHED_FINGERPRINT: tuple | None = None
_CONFIG_MTIME: float | None = None
_HOT_RELOAD = bool(os.getenv("PACE_CONTROL_CONFIG_HOT_RELOAD"))

def _load_yaml(path: Path) -> Dict[str, Any]:
    """ Carrega o conteúdo YAML retornando dicionário vazio em caso de erro """
    if not path.exists():
        return {}
    
    with path.open("r", encoding="utf-8") as handler:
        return yaml.safe_load(handler) or {}
    
def _rate_limit_from(data: Dict[str, Any] | None) -> RateLimitConfig | None:
    """ Normaliza bloco de rate limit e retorna ``None`` se inválido """
    if not isinstance(data, dict):
        return None
    
    try:
        max_requests = int(data.get("max_requests"))
        window = int(data.get("window"))
    except (TypeError, ValueError):
        return None
    
    if max_requests <= 0 or window <= 0:
        return None
    
    return RateLimitConfig(max_requests=max_requests, window=window)

def _token_bucket_from(data: Dict[str, Any] | None) -> TokenBucketConfig:
    """ Constrói configuração de token bucket com fallback para os ``settings`` """
    if not isinstance(data, dict):
        data = {}

    def _float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback
        
    rate = _float(data.get("rate"), scraper_settings.THROTTLE_RATE)
    capacity = _float(data.get("capacity"), scraper_settings.THROTTLE_CAPACITY)
    min_rate = _float(data.get("min_rate"), 0.05)
    decrease_factor = _float(data.get("decrease_factor"), 0.85)
    return TokenBucketConfig(
        rate=rate,
        capacity=capacity,
        min_rate=max(0.0, min_rate),
        decrease_factor=max(0.0, min(decrease_factor, 1.0)),
    )

def _jitter_from(data: Dict[str, Any] | None) -> JitterConfig:
    """ Carrega faixa de jitter com fallback seguro """
    if not isinstance(data, dict):
        data = {}

    def _float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback
        
    jitter_min = _float(data.get("min"), scraper_settings.JITTER_MIN)
    jitter_max = _float(data.get("max"), scraper_settings.JITTER_MAX)

    if jitter_max < jitter_min:
        jitter_min, jitter_max = jitter_max, jitter_min

    return JitterConfig(min=jitter_min, max=jitter_max)

def _human_delay_from(data: Dict[str, Any] | None) -> HumanDelayConfig:
    """ Normaliza blocos de atraso humanizado utilizando variáveis de ambiente como fallback """
    if not isinstance(data, dict):
        data = {}

    def _float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback
        
    avg_wpm = _float(data.get("avg_wpm"), scraper_settings.HUMAN_AVG_WPM)
    base_delay = _float(data.get("base_delay"), scraper_settings.HUMAN_BASE_DELAY)
    fatigue = data.get("fatigue_range")

    fatigue_min = scraper_settings.HUMAN_FATIGUE_MIN
    fatigue_max = scraper_settings.HUMAN_FATIGUE_MAX
    if isinstance(fatigue, (list, tuple)) and len(fatigue) == 2:
        fatigue_min = _float(fatigue[0], fatigue_min)
        fatigue_max = _float(fatigue[1], fatigue_max)

    if fatigue_max < fatigue_min:
        fatigue_min, fatigue_max = fatigue_max, fatigue_min

    return HumanDelayConfig(
        avg_wpm=avg_wpm,
        base_delay=base_delay,
        fatigue_min=fatigue_min,
        fatigue_max=fatigue_max,
    )

def _circuit_breaker_from(data: Dict[str, Any] | None) -> CircuitBreakerConfig:
    """ Cria configuração padrão de circuit breaker, mesmo que ainda não utilizada """
    if not isinstance(data, dict):
        data = {}

    def _int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
        
    failure_threshold = max(1, _int(data.get("failure_threshold"), 5))
    recovery_timeout = max(60, _int(data.get("recovery_timeout"), 300))
    return CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        recovery_time=recovery_timeout,
    )

def _compose_policy(raw: Dict[str, Any], defaults: PaceControlPolicy) -> PaceControlPolicy:
    """ Mescla dados brutos com ``defaults`` produzindo uma política consistente """
    rate_limit = _rate_limit_from(raw.get("rate_limit")) or defaults.rate_limit
    token_bucket = _token_bucket_from(raw.get("token_bucket"))
    jitter = _jitter_from(raw.get("jitter"))
    human_delay = _human_delay_from(raw.get("human_delay"))
    circuit_breaker = _circuit_breaker_from(raw.get("circuit_breaker"))

    return PaceControlPolicy(
        rate_limit=rate_limit,
        token_bucket=token_bucket,
        jitter=jitter,
        human_delay=human_delay,
        circuit_breaker=circuit_breaker,
    )

def _build_settings(data: Dict[str, Any]) -> PaceControlSettings:
    """ Constrói ``PaceControlSettings`` a partir da estrutura YAML normalizada """
    defaults_raw = data.get("deafults") or {}
    defaults_policy = PaceControlPolicy(
        rate_limit=_rate_limit_from(defaults_raw.get("rate_limit"))
        or RateLimitConfig(
            max_requests=scraper_settings.MONITORED_RATE_LIMIT,
            window=scraper_settings.RATE_LIMIT_WINDOW,
        ),
        token_bucket=_token_bucket_from(defaults_raw.get("token_bucket")),
        jitter=_jitter_from(defaults_raw.get("jitter")),
        human_delay=_human_delay_from(defaults_raw.get("human_delay")),
        circuit_breaker=_circuit_breaker_from(defaults_raw.get("circuit_breaker")),
    )

    domains_raw = data.get("domains") or {}
    domains: Dict[str, PaceControlPolicy] = {}
    if isinstance(domains_raw, dict):
        for domain, raw_policy in domains_raw.items():
            if not isinstance(domain, str) or not isinstance(raw_policy, dict):
                continue
            domains[domain.lower()] = _compose_policy(raw_policy, defaults_policy)

    return PaceControlSettings(defaults=defaults_policy, domains=domains)

def _maybe_reload(path: Path) -> None:
    """ Recarrega o arquivo quando `HOT_RELOAD` estiver ativo """
    global _CONFIG_MTIME, _CACHED_SETTINGS, _CACHED_FINGERPRINT

    if not _HOT_RELOAD:
        return
    
    if not path.exists():
        if _CACHED_SETTINGS is not None:
            _CACHED_SETTINGS = None
            _CACHED_FINGERPRINT = None
            _CONFIG_MTIME = None
        return
    
    current_mtime = path.stat().st_mtime
    if _CONFIG_MTIME != current_mtime:
        _CONFIG_MTIME = current_mtime
        _CACHED_SETTINGS = None
        _CACHED_FINGERPRINT = None

def _load_settings() -> PaceControlSettings:
    """ Carrega e cacheia as configurações de pace control """
    global _CACHED_SETTINGS, _CACHED_FINGERPRINT, _CONFIG_MTIME
    
    path = _config_path
    _maybe_reload(path)

    with _CONFIG_LOCK:
        if _CACHED_SETTINGS is not None:
            return _CACHED_SETTINGS
        
        data = _load_yaml(path)
        settings_obj = _build_settings(data)
        _CACHED_SETTINGS = settings_obj
        _CACHED_FINGERPRINT = settings_obj.policy_for(None).fingerprint()
        _CONFIG_MTIME = path.stat().st_mtime if path.exists() else None
        return settings_obj
    
class _SettingsAccessor:
    """ Wrapper que expõe `PaceControlSettings` sob uma interface simples """
    def __call__(self) -> PaceControlSettings:
        """ Permite obter a instância atual utilizando sintaxe de chamada """
        return _load_settings()
    
    def policy_for(self, host: str | None) -> PaceControlPolicy:
        """ Encaminha a resolução da política para o loader interno """
        return _load_settings().policy_for(host)
    
settings = _SettingsAccessor()
