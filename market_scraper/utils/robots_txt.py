""" Parser simples de robots.txt com cache em Redis

Utilitário para leitura resiliente de arquivos robots.txt.
As operações de rede e de acesso ao Redis são executadas em *thread pool*
para evitar bloqueio de loop de eventos.
"""

import requests
import structlog
from urllib.parse import urljoin, urlparse
import re
from typing import Optional
import asyncio

from market_scraper.core.config_scraper import settings
from shared.utils.redis_client import get_redis_client


ROBOTS_CACHE_KEY = settings.ROBOTS_CACHE_KEY
ROBOTS_CACHE_TTL = settings.ROBOTS_CACHE_TTL

logger = structlog.get_logger("robots_txt")

class RobotsTxtParser:
    """ Busca e parseia o robots.txt de um domínio para extrair diretivas como Crawl-delay """
    def __init__(self, base_url: str):
        parsed = urlparse(base_url)
        self.base = f"{parsed.scheme}://{parsed.netloc}"
        self.cache_key = f"{ROBOTS_CACHE_KEY}:{self.base}"
        self.redis = get_redis_client()

    async def _fetch_robots(self) -> str:
        """ Recupera o conteúdo de ``robots.txt`` de forma assíncrona

        A leitura do Redis e a requisição HTTP são executadas em *thread pool*
        para que a função seja utilizada em contextos assíncronos sem
        bloquear o loop de eventos.
        """
        cached = await asyncio.to_thread (self.redis.get, self.cache_key)
        if cached:
            #Se for bytes, decodifica; Se já for str, retorna diretamente
            return cached.decode("utf-8") if isinstance(cached, (bytes, bytearray)) else cached

        url = urljoin(self.base, "/robots.txt")
        try:
            response = await asyncio.to_thread(requests.get, url, timeout=5)
            content = response.text if response.status_code == 200 else ""
        except requests.exceptions.RequestException as e:
            logger.warning("robots_fetch_failed", url=url, error=str(e))
            content = ""

        #Salva no Redis para próximas leituras
        await asyncio.to_thread(self.redis.set, self.cache_key, content, ex=ROBOTS_CACHE_TTL)
        return content

    async def get_crawl_delay(self, user_agent: str = "*") -> Optional[float]:
        """ Retorna o valor de Crawl-Delay (em segundos) para o user_agent definido """
        text = await self._fetch_robots()
        lines = text.splitlines()

        delays = {}
        current_agents = []

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            #Detecta bloco User-agent
            m_agent = re.match(r"(?i)^User-agent:\s*(.+)$", line)
            if m_agent:
                agent = m_agent.group(1).strip()
                current_agents = [agent]
                continue

            #Extrai Crawl-delay dentro do bloco atual
            m_delay = re.match(r"(?i)^Crawl-delay:\s*([0-9]+(?:\.[0-9]+)?)$", line)
            if m_delay and current_agents:
                delay_value = float(m_delay.group(1))
                for agent in current_agents:
                    delays[agent] = delay_value

        #Retorna valor específico ou o wildcard
        if user_agent in delays:
            return delays[user_agent]
        if "*" in delays:
            return delays["*"]
        return None

    async def is_allowed(self, path: str, user_agent: str = "*") -> bool:
        """ Verifica se um ``path`` é permitido para o ``user_agent`` especificado

        O resultado é cacheado no Redis para evitar reprocessamento das diretivas.
        A decisão segue regra da correspondência mais longa: a diretiva
        (``Allow`` ou ``Disallow``) com o *path* mais específico que casar com
        a URL é utilizada. Caso nenhuma regra seja encontrada, o acesso é liberado por padrão.
        """

        #Verifica se já existe resultado em cache para este caminho
        cache_rule_key = f"{self.cache_key}:{user_agent}:{path}"
        cached = await asyncio.to_thread(self.redis.get, cache_rule_key)
        if cached is not None:
            return cached.decode("utf-8") == "1" if isinstance(cached, (bytes, bytearray)) else cached == "1"

        text = await self._fetch_robots()
        lines = text.splitlines()

        rules: dict[str, list[tuple[str, bool]]] = {}
        current_agents: list[str] = []

        for raw in lines:
            line = raw.strip()
            if not line:
                current_agents = []
                continue
            if line.startswith("#"):
                continue

            #Detecta bloco User-agent (pode haver múltiplos seguidos)
            m_agent = re.match(r"(?i)^User-agent:\s*(.+)$", line)
            if m_agent:
                agent = m_agent.group(1).strip()
                current_agents.append(agent)
                continue

            m_rule = re.match(r"(?i)^(Allow|Disallow):\s*(.*)$", line)
            if m_rule and current_agents:
                rule_path = m_rule.group(2).strip()
                is_allow = m_rule.group(1).lower() == "allow"
                for agent in current_agents:
                    rules.setdefault(agent, []).append((rule_path, is_allow))

        #Seleciona regras específicas ou do wildcard
        agent_rules = rules.get(user_agent) or rules.get("*") or []

        def matches(rule: str, target: str) -> bool:
            """ Retorna ``True`` se o ``target`` casa com a regra informada """
            if not rule:
                return True
            if rule.endswith("$"):
                pattern = re.escape(rule[:-1]).replace("\\*", ".*") + "$"
            else:
                pattern = re.escape(rule[:-1]).replace("\\*", ".*")
            return re.match("^" + pattern, target) is not None

        allowed = True
        best_len = -1
        for rule_path, is_allow in agent_rules:
            if matches(rule_path, path):
                rule_len = len(rule_path)
                if rule_len > best_len:
                    best_len = rule_len
                    allowed = is_allow

        await asyncio.to_thread(
            self.redis.set, cache_rule_key, "1" if allowed else "0", ex=ROBOTS_CACHE_TTL
        )
        return allowed
