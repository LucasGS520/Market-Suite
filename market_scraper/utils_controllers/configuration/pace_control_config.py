""" Loader de configuração para o controle de ritmo do scraper """

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from market_scraper.core.config_scraper import settings as scraper_settings
from market_scraper.utils_controllers.configuration.base_loader import HotReloadSettingsStore


__all__ = [
    "RateLimitConfig",
    "TokenBucketConfig",
    "JitterConfig",
    "HumanDelayConfig",
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
class PaceControlPolicy:
    """ Agrega todas as configurações necessárias para o controle de ritmo """
    rate_limit: RateLimitConfig | None
    token_bucket: TokenBucketConfig
    jitter: JitterConfig
    human_delay: HumanDelayConfig

    def fingerprint(self) -> tuple:
        """ Retorna assinatura imutável da política para permitir cache seguro """
        rate_tuple = (0, 0)
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
        
    jitter_min = _float(
        data.get("min", data.get("min_delay")),
        scraper_settings.JITTER_MIN,
    )
    jitter_max = _float(
        data.get("max", data.get("max_delay")),
        scraper_settings.JITTER_MAX,
    )

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

def _compose_policy(raw: Dict[str, Any], defaults: PaceControlPolicy) -> PaceControlPolicy:
    """ Mescla dados brutos com ``defaults`` produzindo uma política consistente """
    rate_limit = _rate_limit_from(raw.get("rate_limit")) or defaults.rate_limit
    token_bucket = _token_bucket_from(raw.get("token_bucket"))
    jitter = _jitter_from(raw.get("jitter"))
    human_delay = _human_delay_from(raw.get("human_delay"))

    return PaceControlPolicy(
        rate_limit=rate_limit,
        token_bucket=token_bucket,
        jitter=jitter,
        human_delay=human_delay,
    )

def _build_settings(data: Dict[str, Any]) -> PaceControlSettings:
    """ Constrói ``PaceControlSettings`` a partir da estrutura YAML normalizada """
    defaults_raw = data.get("defaults") or {}
    defaults_policy = PaceControlPolicy(
        rate_limit=_rate_limit_from(defaults_raw.get("rate_limit"))
        or RateLimitConfig(
            max_requests=scraper_settings.MONITORED_RATE_LIMIT,
            window=scraper_settings.RATE_LIMIT_WINDOW,
        ),
        token_bucket=_token_bucket_from(defaults_raw.get("token_bucket")),
        jitter=_jitter_from(defaults_raw.get("jitter")),
        human_delay=_human_delay_from(defaults_raw.get("human_delay")),
    )

    domains_raw = data.get("domains") or {}
    domains: Dict[str, PaceControlPolicy] = {}
    if isinstance(domains_raw, dict):
        for domain, raw_policy in domains_raw.items():
            if not isinstance(domain, str) or not isinstance(raw_policy, dict):
                continue
            domains[domain.lower()] = _compose_policy(raw_policy, defaults_policy)

    return PaceControlSettings(defaults=defaults_policy, domains=domains)

_SETTINGS_STORE = HotReloadSettingsStore[
    PaceControlSettings
](
    default_path=Path(__file__).with_name("pace_control.yaml"),
    env_var="PACE_CONTROL_CONFIG_FILE",
    hot_reload_env="PACE_CONTROL_CONFIG_HOT_RELOAD",
    builder=_build_settings,
)

def _load_settings() -> PaceControlSettings:
    """ Carrega as configurações de pace control utilizando cache compartilhado """
    return _SETTINGS_STORE.get()
    
class _SettingsAccessor:
    """ Wrapper que expõe `PaceControlSettings` sob uma interface simples """
    def __call__(self) -> PaceControlSettings:
        """ Permite obter a instância atual utilizando sintaxe de chamada """
        return _SETTINGS_STORE.get()
    
    def policy_for(self, host: str | None) -> PaceControlPolicy:
        """ Encaminha a resolução da política para o loader interno """
        return _SETTINGS_STORE.get().policy_for(host)

    def reload(self) -> PaceControlSettings:
        """ Força a recarga das configurações de pace control """
        return _SETTINGS_STORE.reload()

settings = _SettingsAccessor()
