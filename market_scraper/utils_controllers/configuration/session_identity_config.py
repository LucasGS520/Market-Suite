""" Loader de configuração para o gerenciador de identidade de sessão """

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from market_scraper.utils.constants import GENERIC_COOKIES
from market_scraper.utils_controllers.configuration.base_loader import HotReloadSettingsStore


__all__ = [
    "UserAgentConfig",
    "CookieTemplateConfig",
    "SessionIdentityPolicy",
    "SessionIdentitySettings",
    "settings",
]

@dataclass(frozen=True)
class UserAgentConfig:
    """ Configuração de rotação de User-Agent """
    max_requests: int
    session_timeout: int

@dataclass(frozen=True)
class CookieTemplateConfig:
    """ Modelo de cookies inciais aplicado ao iniciar uma sessão """
    template: Dict[str, str]

@dataclass(frozen=True)
class SessionIdentityPolicy:
    """ Agrupa as configurações utilizadas pelo ``SessionIdentityManager`` """
    user_agent: UserAgentConfig
    cookie_template: CookieTemplateConfig

    def fingerprint(self) -> tuple[int, int, tuple[tuple[str, str], ...]]:
        """ Retorna assinatura imutável da política para facilitar cache """
        cookies_signature = tuple(sorted(self.cookie_template.template.items()))
        return (
            self.user_agent.max_requests,
            self.user_agent.session_timeout,
            cookies_signature,
        )

class SessionIdentitySettings:
    """ Representa o conjunto de políticas carregadas do YAML """
    def __init__(self, *, defaults: SessionIdentityPolicy, domains: Dict[str, SessionIdentityPolicy]) -> None:
        self._defaults = defaults
        self._domains = domains

    def policy_for(self, host: str | None) -> SessionIdentityPolicy:
        """ Retorna a política aplicável ao host infomado """
        if not host:
            return self._defaults
        
        host = host.lower()
        for domain, policy in self._domains.items():
            if host == domain or host.endswith("." + domain):
                return policy
        return self._defaults
    
def _user_agent_from(data: Dict[str, Any] | None) -> UserAgentConfig:
    """ Normaliza o bloco de configuração de User-Agent """
    if not isinstance(data, dict):
        data = {}

    def _int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
        
    max_requests = max(1, _int(data.get("max_requests"), 50))
    session_timeout = max(60, _int(data.get("session_timeout"), 3600))
    return UserAgentConfig(max_requests=max_requests, session_timeout=session_timeout)

def _cookies_from(data: Dict[str, Any] | None) -> CookieTemplateConfig:
    """ Cria template de cookies utilizando fallback seguro """
    if isinstance(data, dict):
        template_raw = data.get("template")
    else:   
        template_raw = None
    
    template: Dict[str, str] = {}
    if isinstance(template_raw, dict):
        template = {str(key): str(value) for key, value in template_raw.items()}
    else:
        template = {key: str(value) for key, value in GENERIC_COOKIES.items()}

    return CookieTemplateConfig(template=template)

def _build_settings(data: Dict[str, Any]) -> SessionIdentitySettings:
    """ Transforma os dados carregados em ``SessionIdentitySettings`` """
    defaults_raw = data.get("defaults") or {}
    defaults = SessionIdentityPolicy(
        user_agent=_user_agent_from(defaults_raw.get("user_agent")),
        cookie_template=_cookies_from(defaults_raw.get("cookies")),
    )

    domains_raw = data.get("domains") or {}
    domains: Dict[str, SessionIdentityPolicy] = {}
    if isinstance(domains_raw, dict):
        for domain, raw_policy in domains_raw.items():
            if not isinstance(domain, str) or not isinstance(raw_policy, dict):
                continue
            domains[domain.lower()] = SessionIdentityPolicy(
                user_agent=_user_agent_from(raw_policy.get("user_agent")),
                cookie_template=_cookies_from(raw_policy.get("cookies")),
            )

    return SessionIdentitySettings(defaults=defaults, domains=domains)

_SETTINGS_STORE = HotReloadSettingsStore[
    SessionIdentitySettings
](
    default_path=Path(__file__).with_name("session_identity.yaml"),
    env_var="SESSION_IDENTITY_CONFIG_FILE",
    hot_reload_env="SESSION_IDENTITY_CONFIG_HOT_RELOAD",
    builder=_build_settings,
)

def _load_settings() -> SessionIdentitySettings:
    """ Carrega as configurações de identidade de sessão utilizando cache unificado """
    return _SETTINGS_STORE.get()
    
class _SettingsAccessor:
    """ Proxy para expor as configurações atuais """
    def __call__(self) -> SessionIdentitySettings:
        """ Retorna a instância atual carregada """
        return _SETTINGS_STORE.get()
    
    def policy_for(self, host: str | None) -> SessionIdentityPolicy:
        """ Recupera a política aplicável ao host """
        return _SETTINGS_STORE.get().policy_for(host)

    def reload(self) -> SessionIdentitySettings:
        """ Força a recarga das políticas configuradas """
        return _SETTINGS_STORE.reload()
    
settings = _SettingsAccessor()
