""" Centraliza a escolha de User-Agent e a composição de headers HTTP 

O módulo oferece uma única fonte para os identificadores utilizados
pelo scraper. Mantemos um round-robin determinístico para o 
pool configurado e caches simples por domínio/sessão, garantindo
previsibilidade sem depender de bibliotecas externas ou chamadas síncronas.
"""

from __future__ import annotations

import itertools
import threading
from typing import Dict, Iterator
from urllib.parse import urlparse

from market_scraper.core.config_scraper import settings


__all__ = ["get_user_agent", "compose_headers", "reset_user_agent_state"]

_POOL_LOCK = threading.Lock()
_POOL_ITERATOR: Iterator[str] | None = None
_DOMAIN_AFFINITY: Dict[str, str] = {}
_SESSION_AFFINITY: Dict[str, str] = {}

def _build_cycle() -> Iterator[str]:
    """ Gera um iterador infinito respeitando o pool configurado """
    pool = settings.SCRAPER_USER_AGENT_POOL
    if not pool:
        return itertools.cycle((settings.SCRAPER_DEFAULT_USER_AGENT,))
    return itertools.cycle(pool)

def _ensure_cycle() -> Iterator[str]:
    """ Garante que o iterador do round-robin esteja inicializado """
    global _POOL_ITERATOR
    if _POOL_ITERATOR is None:
        _POOL_ITERATOR = _build_cycle()
    return _POOL_ITERATOR

def _next_user_agent_unlocked() -> str:
    """ Obtém o próximo User-Agent respeitando o round-robin """
    iterator = _ensure_cycle()
    try:
        return next(iterator)
    except StopIteration:
        _reset_cycle()
        return next(_ensure_cycle())
    
def _reset_cycle() -> None:
    """ Reconstrói o iterador do round-robin (usado em testes) """
    global _POOL_ITERATOR
    _POOL_ITERATOR = _build_cycle()

def _normalize_domain(value: str | None) -> str | None:
    """ Normaliza uma string para domínio em minúsculas """
    if not value:
        return None
    
    parsed = urlparse(value)
    host = parsed.hostname
    if host:
        return host.lower()
    
    stripped = value.strip().split("/")[0]
    return stripped.lower() if stripped else None

def get_user_agent(
    domain_or_url: str | None = None,
    *,
    session_id: str | None = None,
) -> str:
    """ Retorna um User-Agent determinístico para requisição atual
    
    A escolha prioriza afinidade com a sessão (quando informada) e com o
    domínio alvo. Ausência de afinidade resulta em round-robin simples.
    """
    normalized_domain = _normalize_domain(domain_or_url)
    with _POOL_LOCK:
        if session_id:
            key = session_id
            cached = _SESSION_AFFINITY.get(key)
            if cached:
                return cached
            
            agent = _next_user_agent_unlocked()
            _SESSION_AFFINITY[key] = agent
            return agent
        
        if normalized_domain:
            cached = _DOMAIN_AFFINITY.get(normalized_domain)
            if cached:
                return cached
            
            agent = _next_user_agent_unlocked()
            #Mantemos o vínculo por domínio para reaproveitar o mesmo agente em chamadas subsequentes
            _DOMAIN_AFFINITY[normalized_domain] = agent
            return agent
        
        return _next_user_agent_unlocked()
    
def compose_headers(user_agent: str, *, referer: str | None = None) -> Dict[str, str]:
    """ Produz o conjunto mínimo de headers coerentes com o User-Agent """
    headers = {
        "User-Agent": user_agent,
        "Accept": settings.SCRAPER_HEADERS_ACCEPT,
        "Accept-Language": settings.SCRAPER_HEADERS_ACCEPT_LANGUAGE,
        "Connection": settings.SCRAPER_HEADERS_CONNECTION,
        "Cache-Control": settings.SCRAPER_HEADERS_CACHE_CONTROL,
    }

    accept_encoding = settings.SCRAPER_HEADERS_ACCEPT_ENCODING
    if accept_encoding:
        headers["Accept-Encoding"] = accept_encoding

    if referer:
        headers["Referer"] = referer

    #Acrescenta headers opcionais configurados para domínios específicos
    for key, value in settings.get_additional_headers().items():
        headers[key] = value

    return headers

def reset_user_agent_state() -> None:
    """ Reinicia caches internos e o round-robin (usado em testes) """
    with _POOL_LOCK:
        _DOMAIN_AFFINITY.clear()
        _SESSION_AFFINITY.clear()
        _reset_cycle()
