""" Gerencia User-Agent e cookies de forma centralizada por sessão/domínio """

from __future__ import annotations

import threading
import time
import random
from dataclasses import dataclass
from typing import Dict

import httpx
from requests import Response, cookies

from market_scraper.utils.config.session_identity import (
    SessionIdentityPolicy,
    settings as identity_settings,
)
from market_scraper.utils.constants import USER_AGENTS


@dataclass
class _UserAgentState:
    """ Estado interno utilizado para controlar rotação de User-Agent """
    value: str
    count: int
    start_time: float
    signature: tuple[int, int]

@dataclass
class _CookiesState:
    """ Armazena cookies gerados e a assinatura da política vigente """
    jar: cookies.RequestsCookieJar
    signature: tuple[int, int]

class SessionIdentityManager:
    """ Coordena identidade de sessão reutilizável pelo scraper """
    def __init__(self) -> None:
        self._user_agents: Dict[str, _UserAgentState] = {}
        self._cookies: Dict[str, _CookiesState] = {}
        self._lock = threading.Lock()

    def _policy_signature(self, policy: SessionIdentityPolicy) -> tuple[int, int]:
        """ Gera assinatura estável da política para detectar alterações """
        ua = policy.user_agent
        return (ua.max_requests, ua.session_timeout)
    
    def _session_key(self, session_id: str, *, host: str | None) -> str:
        """ Normaliza chave composta por domínio e identificador de sessão """
        domain = (host or "default").lower()
        return f"{domain}:{session_id}" if session_id else domain
    
    def get_user_agent(self, session_id: str, *, host: str | None = None) -> str:
        """ Retorna User-Agent associado à sessão, rotacionando quando necessário """
        policy = identity_settings.policy_for(host)
        signature = self._policy_signature(policy)
        key = self._session_key(session_id, host)
        now = time.monotonic()

        with self._lock:
            state = self._user_agents.get(key)
            if (
                state is None
                or state.count >= policy.user_agent.max_requests
                or (now - state.start_time) >= policy.user_agent.session_timeout
            ): 
                value = random.choice(USER_AGENTS)
                state = _UserAgentState(
                    value=value,
                    count=0,
                    start_time=now,
                    signature=signature,
                )
                self._user_agents[key] = state

            state.count += 1
            return state.value
        
    def rotate_user_agent(self, session_id: str | None = None, *, host: str | None = None) -> None:
        """ Força a troca do User-Agent da sessão informada """
        with self._lock:
            if session_id is None:
                self._user_agents.clear()
            else:
                key = self._session_key(session_id, host)
                self._user_agents.pop(key, None)

    def get_cookies(self, session_id: str, *, host: str | None = None) -> cookies.RequestsCookieJar:
        """ Recupera jar de cookies respeitando template configurado """
        policy = identity_settings.policy_for(host)
        signature = self._policy_signature(policy)
        key = self._session_key(session_id, host)

        with self._lock:
            state = self._cookies.get(key)
            if state is None or state.signature != signature:
                jar = cookies.cookiejar_from_dict(policy.cookies.template.copy())
                state = _CookiesState(jar=jar, signature=signature)
                self._cookies[key] = state
            return state.jar
        
    def update_cookies(
        self,
        session_id: str,
        response: Response | httpx.Response | None,
        *,
        host: str | None = None,
    ) -> None:
        """ Atualiza cookies salvos utilizando uma resposta HTTP recente """
        if response is None:
            return
        jar = self.get_cookies(session_id, host=host)
        jar.update(response.cookies)

    def reset_cookies(self, session_id: str | None = None, *, host: str | None = None) -> None:
        """ Limpa cookies armazenados para a sessão ou domínio informado """
        with self._lock:
            if session_id is None:
                if host is None:
                    self._cookies.clear()
                else:
                    prefix = f"{host.lower()}:"
                    keys = [key for key in self._cookies if key.startswith(prefix)]
                    for key in keys:
                        self._cookies.pop(key, None)
            else:
                key = self._session_key(session_id, host)
                self._cookies.pop(key, None)

    def purge_expired(self) -> None:
        """ Remove sessões cujo timeout já expirou """
        now = time.monotonic()
        with self._lock:
            expired_ua = [
                key
                for key, state in self._user_agents.items()
                if (now - state.start_time) >= state.signature[1]
            ]
            for key in expired_ua:
                self._user_agents.pop(key, None)

            expired_cookies = [
                key
                for key, state in self._cookies.items()
                if state.signature
                != self._policy_signature(
                    identity_settings.policy_for(
                        None if (domain_part := key.split(":", 1)[0]) == "default" else domain_part
                    )
                )
            ]
            for key in expired_cookies:
                self._cookies.pop(key, None)

#Instância compartilhada para reutilização entre módulos
session_identity_manager = SessionIdentityManager()
