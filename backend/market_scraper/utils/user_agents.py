""" Adaptadores do serviço de scraping para uso compartilhado de User-Agent """

from __future__ import annotations

from typing import Dict, Tuple

from shared.utils.user_agents import UserAgentProvider

from market_scraper.core.config_scraper import settings


__all__ = ["get_user_agent", "compose_headers", "reset_user_agent_state"]

def _build_base_headers() -> Dict[str, str]:
    """ Monta headers mínimos a partir das configurações ativas """
    return {
        "Accept": settings.SCRAPER_HEADERS_ACCEPT,
        "Accept-Language": settings.SCRAPER_HEADERS_ACCEPT_LANGUAGE,
        "Connection": settings.SCRAPER_HEADERS_CONNECTION,
        "Cache-Control": settings.SCRAPER_HEADERS_CACHE_CONTROL,
    }

def _build_provider() -> UserAgentProvider:
    """ Instancia ``UserAgentProvider`` refletindo configurações atuais """
    return UserAgentProvider(
        default_user_agent=settings.SCRAPER_DEFAULT_USER_AGENT,
        user_agent_pool=settings.SCRAPER_USER_AGENT_POOL,
        base_headers=_build_base_headers(),
        additional_headers_factory=settings.get_additional_headers,
    )

_provider: UserAgentProvider | None = None
_provider_config: Tuple[str, Tuple[str, ...], Dict[str, str]] | None = None


def _current_config() -> Tuple[str, Tuple[str, ...], Dict[str, str]]:
    """ Captura as configurações relevantes do pool atual """
    return (
        settings.SCRAPER_DEFAULT_USER_AGENT,
        settings.SCRAPER_USER_AGENT_POOL,
        _build_base_headers(),
    )

def _ensure_provider() -> UserAgentProvider:
    """ Garante instância sincronizada com as configurações atuais """
    global _provider, _provider_config
    config = _current_config()
    if _provider is None or _provider_config != config:
        _provider = _build_provider()
        _provider_config = config
    return _provider

def get_user_agent(
    domain_or_url: str | None = None,
    *,
    session_id: str | None = None,
) -> str:
    """ Retorna User-Agent determinístico alinhado às configurações do scraper """
    provider = _ensure_provider()
    return provider.get_user_agent(domain_or_url, session_id=session_id)
    
def compose_headers(user_agent: str, *, referer: str | None = None) -> Dict[str, str]:
    """ Produz cabeçalhos coerentes com o User-Agent e políticas do scraper """
    provider = _ensure_provider()
    headers = provider.compose_headers(user_agent, referer=referer)
    
    accept_encoding = settings.SCRAPER_HEADERS_ACCEPT_ENCODING
    if accept_encoding:
        headers["Accept-Encoding"] = accept_encoding

    return headers

def reset_user_agent_state() -> None:
    """ Reinicia o estado interno para facilitar cenários de teste """
    global _provider, _provider_config
    _provider = None
    _provider_config = None
    