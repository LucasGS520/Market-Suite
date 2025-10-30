""" Garencia rotação e composição de User-Agent compartilhada """

from __future__ import annotations

import itertools
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Dict, Iterator
from urllib.parse import urlparse

def _build_cycle(default_user_agent: str, user_agent_pool: Sequence[str]) -> Iterator[str]:
    """ Monta o ciclo determinístico respeitando o pool configurado """
    filtered_pool = tuple(agent for agent in user_agent_pool if agent)
    if not filtered_pool:
        return itertools.cycle((default_user_agent))
    return itertools.cycle(filtered_pool)

def _normalize_domain(domain_or_url: str | None) -> str | None:
    """ Converte valores livres em domínio minúsculo reutilizável """
    if not domain_or_url:
        return None
    
    parsed = urlparse(domain_or_url)
    host = parsed.hostname
    if host:
        return host.lower()
    
    stripped = domain_or_url.strip().split("/")[0]
    return stripped.lower() if stripped else None

class UserAgentProvider:
    """ Expõe API thread-safe para rotação de User-Agent e headers """
    def __init__(
        self,
        *,
        default_user_agent: str,
        user_agent_pool: Sequence[str],
        base_headers: Mapping[str, str] | None = None,
        additional_headers_factory: Callable[[], Mapping[str, str]] | None = None,
    ) -> None:
        self._default_user_agent = default_user_agent
        self._user_agent_pool = tuple(user_agent_pool)
        self._base_headers = dict(base_headers or {})
        self._additional_headers_factory = additional_headers_factory
        self._pool_lock = threading.Lock()
        self._pool_iterator: Iterator[str] = _build_cycle(
            self._default_user_agent,
            self._user_agent_pool,
        )
        self._domain_affinity: Dict[str, str] = {}
        self._session_affinity: Dict[str, str] = {}

    def _next_user_agent_unlocked(self) -> str:
        """ Obtém o próximo User-Agent respeitando o round-robin """
        try:
            return next(self._pool_iterator)
        except StopIteration:
            self._pool_iterator = _build_cycle(
                self._default_user_agent,
                self._user_agent_pool,
            )
            return next(self._pool_iterator)
        
    def get_user_agent(
        self,
        domain_or_url: str | None = None,
        *,
        session_id: str | None = None,
    ) -> str:
        """ Retorna User-Agent determinístico reutilizando afinidades """
        normalized_domain = _normalize_domain(domain_or_url)
        with self._pool_lock:
            if session_id:
                cached = self._session_affinity.get(session_id)
                if cached:
                    return cached
                
                agent = self._next_user_agent_unlocked()
                self._session_affinity[session_id] = agent
                return agent
            
            if normalized_domain:
                cached = self._domain_affinity.get(normalized_domain)
                if cached:
                    return cached
                
                agent = self._next_user_agent_unlocked()
                self._domain_affinity[normalized_domain] = agent
                return agent
            
            return self._next_user_agent_unlocked()
        
    def compose_headers(
        self,
        user_agent: str,
        *, 
        referer: str | None = None,
    ) -> Dict[str, str]:
        """ Monta cabeçalhos consistentes com o User-Agent fornecido """
        headers = {"User-Agent": user_agent, **self._base_headers}
        if referer:
            headers["Referer"] = referer

        if self._additional_headers_factory is not None:
            for key, value in self._additional_headers_factory().items():
                headers[key] = value

        return headers
    
    def reset_state(self) -> None:
        """ Reinicia caches e ciclos de User-Agent (útil em testes) """
        with self._pool_lock:
            self._domain_affinity.clear()
            self._session_affinity.clear()
            self._pool_iterator = _build_cycle(
                self._default_user_agent,
                self._user_agent_pool,
            )

        
__all__ = [
    "UserAgentProvider",
]
