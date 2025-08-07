""" Gerencia rotação de User-Agent por sessão para reduzir bloqueios """

import random
import time
import threading

from scraper_app.utils.constants import USER_AGENTS


class IntelligentUserAgentManager:
    """ Gerencia user-agents rotativos por sessão com limites de uso """

    def __init__(self, max_requests: int = 50, session_timeout: int = 3600):
        self.max_requests = max_requests
        self.session_timeout = session_timeout
        self.sessions: dict[str, dict] = {}
        self.lock = threading.Lock()

    def get_user_agent(self, session_id: str) -> str:
        """ Retorna o user-agent da sessão, rotacionando quando necessário """
        now = time.monotonic()
        with self.lock:
            sess = self.sessions.get(session_id)
            if (
                sess is None
                or sess["count"] >= self.max_requests
                or (now - sess["start_time"]) >= self.session_timeout
            ):
                ua = random.choice(USER_AGENTS)
                sess = {"ua": ua, "count": 0, "start_time": now}
                self.sessions[session_id] = sess
            sess["count"] += 1
            return sess["ua"]

    def reset(self, session_id: str) -> None:
        """ Reseta o estado de uma sessão específica """
        with self.lock:
            self.sessions.pop(session_id, None)

    def rotate(self, session_id: str | None = None) -> None:
        """ Força a troca do user-agent de uma ou todas as sessões """
        with self.lock:
            if session_id is None:
                self.sessions.clear()
            else:
                self.sessions.pop(session_id, None)
