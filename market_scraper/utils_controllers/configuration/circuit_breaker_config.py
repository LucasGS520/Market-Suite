""" Loader de configuração para o Circuit Breaker por domínio """

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from market_scraper.utils_controllers.configuration.base_loader import HotReloadSettingsStore


__all__ = [
    "CircuitBreakerPolicy",
    "CircuitBreakerSettings",
    "settings",
]

@dataclass(frozen=True)
class CircuitBreakerPolicy:
    """ Representa a política aplicada a um domínio específico """
    failure_threshold: int
    recovery_time: int

    def fingerprint(self) -> tuple[int, int]:
        """ Retorna assinatura imutável para detecção de alterações """
        return (self.failure_threshold, self.recovery_time)
    
class CircuitBreakerSettings:
    """ Armazena política padrão e políticas específicas por domínio """
    def __init__(self, *, defaults: CircuitBreakerPolicy, domains: Dict[str, CircuitBreakerPolicy]) -> None:
        self._defaults = defaults
        self._domains = domains

    def policy_for(self, host: str | None) -> CircuitBreakerPolicy:
        """ Seleciona a política adequada para o domínio informado """
        if not host:
            return self._defaults
        
        host = host.lower()
        for domain, policy in self._domains.items():
            if host == domain or host.endswith("." + domain):
                return policy
        return self._defaults
    
def _policy_from(data: Dict[str, Any] | None) -> CircuitBreakerPolicy:
    """ Normaliza bloco de configuração em :class:`CircuitBreakerPolicy` """
    if not isinstance(data, dict):
        data = {}

    def _int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
        
    failure_threshold = max(1, _int(data.get("failure_threshold"), 5))
    recovery_time = max(60, _int(data.get("recovery_time"), 300))
    return CircuitBreakerPolicy(
        failure_threshold=failure_threshold,
        recovery_time=recovery_time,
    )

def _build_settings(data: Dict[str, Any]) -> CircuitBreakerSettings:
    """ Transforma dicionário bruto em :class:`CircuitBreakerSettings` """
    defaults = _policy_from(data.get("defaults"))
    domains_raw = data.get("domains") or {}

    domains: Dict[str, CircuitBreakerPolicy] = {}
    if isinstance(domains_raw, dict):
        for domain, raw_policy in domains_raw.items():
            if not isinstance(domain, str):
                continue
            domains[domain.lower()] = _policy_from(raw_policy)

    return CircuitBreakerSettings(defaults=defaults, domains=domains)

_SETTINGS_STORE = HotReloadSettingsStore[
    CircuitBreakerSettings
](
    default_path=Path(__file__).with_name("circuit_breaker.yaml"),
    env_var="CIRCUIT_CONFIG_FILE",
    hot_reload_env="CIRCUIT_BREAKER_CONFIG_HOT_RELOAD",
    builder=_build_settings,
)

def _load_settings() -> CircuitBreakerSettings:
    """ Carrega configurações aplicando cache compartilhado e hot-reload automático """
    return _SETTINGS_STORE.get()

class _SettingsAccessor:
    """ Wrapper que expõe as configurações atuais sob interface simple """
    def __call__(self) -> CircuitBreakerSettings:
        """ Permite obter ``CircuitBreakerSetting`` usando sintaxe de chamada """
        return _SETTINGS_STORE.get()
    
    def policy_for(self, host: str | None) -> CircuitBreakerPolicy:
        """ Encaminha para :meth:`CircuitBreakerSettings.policy_for` """
        return _SETTINGS_STORE.get().policy_for(host)

    def reload(self) -> CircuitBreakerSettings:
        """ Força a recarga das configurações do circuit breaker """
        return _SETTINGS_STORE.reload()

settings = _SettingsAccessor()
