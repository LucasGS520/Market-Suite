""" Loader de configuração para o Circuit Breaker por domínio

O objetivo é isolar a definição de limites e tempos de recuperação utilizados
pelas instâncias de :class:`~market_scraper.utils.circuit_breaker.DomainCircuitBreaker`
Cada domínio pode especificar parâmetros próprios no arquivo YAML, permitindo
ajustes finos sem necessidade de alterar o código-fonte.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
import threading
import os

import yaml


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
    
def _config_path() -> Path:
    """ Resolve caminho do YAML considerando overrides por ambiente """
    default = Path(__file__).with_name("circuit_breaker.yaml")
    raw_path = os.getenv("CIRCUIT_CONFIG_FILE")
    if raw_path:
        return Path(raw_path)
    return default

def _load_yaml(path: Path) -> Dict[str, Any]:
    """ Carrega o YAML retornando dicionário vazio em caso de erro """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handler:
        return yaml.safe_load(handler) or {}
    
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

_CONFIG_LOCK = threading.Lock()
_CACHED_SETTINGS: CircuitBreakerSettings | None = None
_CONFIG_MTIME: float | None = None
_TRUTHY_HOT_RELOAD_VALUES = {"1", "true", "yes", "y", "on", "t"}

def _parse_hot_reload_flag(raw_value: str | None) -> bool:
    """ Interpreta a flag de hot-reload aceitando apenas valores afirmativos """
    if raw_value is None:
        return False
    
    return raw_value.strip().lower() in _TRUTHY_HOT_RELOAD_VALUES

_HOT_RELOAD = _parse_hot_reload_flag(os.getenv("CIRCUIT_BREAKER_CONFIG_HOT_RELOAD"))

def _maybe_reload(path: Path) -> None:
    """ Limpa cache quando o hot-reload está ativado e o arquivo foi modificado """
    global _CACHED_SETTINGS, _CONFIG_MTIME

    if not _HOT_RELOAD:
        return
    
    if not path.exists():
        _CACHED_SETTINGS = None
        _CONFIG_MTIME = None
        return
    
    current_mtime = path.stat().st_mtime
    if _CONFIG_MTIME != current_mtime:
        _CACHED_SETTINGS = None
        _CONFIG_MTIME = current_mtime

def _load_settings() -> CircuitBreakerSettings:
    """ Carrega configurações aplicando cache thread-safe """
    global _CACHED_SETTINGS, _CONFIG_MTIME

    path = _config_path()
    _maybe_reload(path)

    with _CONFIG_LOCK:
        if _CACHED_SETTINGS is not None:
            return _CACHED_SETTINGS
        
        data = _load_yaml(path)
        settings_obj = _build_settings(data)
        _CACHED_SETTINGS = settings_obj
        _CONFIG_MTIME = path.stat().st_mtime if path.exists() else None
        return settings_obj
    
class _SettingsAccessor:
    """ Wrapper que expõe as configurações atuais sob interface simple """
    def __call__(self) -> CircuitBreakerSettings:
        """ Permite obter ``CircuitBreakerSetting`` usando sintaxe de chamada """
        return _load_settings()
    
    def policy_for(self, host: str | None) -> CircuitBreakerPolicy:
        """ Encaminha para :meth:`CircuitBreakerSettings.policy_for` """
        return _load_settings().policy_for(host)

settings = _SettingsAccessor()