""" Parser resiliente de ``robots.txt`` com cache integrado

Todas as configurações relevantes (prefixo de cache, TTL e timeout das
requisições) ficam concentradas neste módulo para reduzir o número de
arquivos necessários. O parser executa operações de rede em *thread pool*
para não bloquear o loop assíncrono principal e usa Redis quando disponível.
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
import structlog

from market_scraper.core.config_scraper import settings

from shared.utils.redis_client import get_redis_client
from shared.utils.logging_utils import sanitize_log_data

#Parâmetros padrão definidos em código para simplificar manutenção
DEFAULT_CACHE_PREFIX = settings.ROBOTS_CACHE_KEY
DEFAULT_CACHE_TTL = int(settings.ROBOTS_CACHE_TTL)
DEFAULT_REQUEST_TIMEOUT = 5

logger = structlog.get_logger("robots_txt")

class RobotsTxtParser:
    """ Busca e interpreta regras declaradas no ``robots.txt`` de um domínio """
    def __init__(
        self,
        base_url: str,
        *,
        cache_prefix: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        request_timeout: Optional[int] = None,
    ) -> None:
        """ Normaliza o domínio e define parâmetros de cache e timeout """
        parsed = urlparse(base_url)
        self.base = f"{parsed.scheme}://{parsed.netloc}"
        self.cache_prefix = cache_prefix or DEFAULT_CACHE_PREFIX
        self.cache_ttl = int(cache_ttl) if cache_ttl is not None else DEFAULT_CACHE_TTL
        self.request_timeout = float(request_timeout) if request_timeout is not None else DEFAULT_REQUEST_TIMEOUT
        self.cache_key = f"{self.cache_prefix}:{self.base}"
        #Cliente Redis compartilhado entre instâncias; ``None`` indica fallback local
        self.redis = get_redis_client()

    async def _fetch_robots(self, user_agent: str) -> str:
        """ Baixa o ``robots.txt`` respeitando o ``user-agent`` informado """
        cache_key = f"{self.cache_key}:{user_agent}"

        cached = None
        if self.redis is not None:
            cached = await asyncio.to_thread(self.redis.get, cache_key)

        if cached:
            return cached.decode("utf-8") if isinstance(cached, (bytes, bytearray)) else cached

        url = urljoin(self.base, "/robots.txt")
        headers = {"User-Agent": user_agent}
        try:
            response = await asyncio.to_thread(
                requests.get,
                url,
                timeout=self.request_timeout,
                headers=headers,
            )
            content = response.text if response.status_code == 200 else ""
        except requests.exceptions.RequestException as err:
            logger.warning("robots_fetch_failed", url=sanitize_log_data(url), error=sanitize_log_data(str(err)))
            content = ""

        if self.redis is not None:
            await asyncio.to_thread(self.redis.set, cache_key, content, ex=self.cache_ttl)
        return content

    async def get_crawl_delay(self, user_agent: str = "*") -> Optional[float]:
        """ Retorna o valor de Crawl-Delay (em segundos) para o user_agent definido """
        text = await self._fetch_robots(user_agent)
        lines = text.splitlines()

        delays = {}
        current_agents: list[str] = []

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            match_agent = re.match(r"(?i)^User-agent:\s*(.+)$", line)
            if match_agent:
                agent = match_agent.group(1).strip()
                current_agents = [agent]
                continue

            match_delay = re.match(r"(?i)^Crawl-delay:\s*([0-9]+(?:\.[0-9]+)?)$", line)
            if match_delay and current_agents:
                delay_value = float(match_delay.group(1))
                for agent in current_agents:
                    delays[agent] = delay_value

        if user_agent in delays:
            return delays[user_agent]
        if "*" in delays:
            return delays["*"]
        return None

    async def is_allowed(self, path: str, user_agent: str = "*") -> bool:
        """ Avalia se o ``path`` é permitido para o ``user_agent`` informado """
        cache_rule_key = f"{self.cache_key}:{user_agent}:{path}"

        cached = None
        if self.redis is not None:
            cached = await asyncio.to_thread(self.redis.get, cache_rule_key)

        if cached is not None:
            return cached.decode("utf-8") == "1" if isinstance(cached, (bytes, bytearray)) else cached == "1"

        text = await self._fetch_robots(user_agent)
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

            match_agent = re.match(r"(?i)^User-agent:\s*(.+)$", line)
            if match_agent:
                agent = match_agent.group(1).strip()
                current_agents.append(agent)
                continue

            match_rule = re.match(r"(?i)^(Allow|Disallow):\s*(.*)$", line)
            if match_rule and current_agents:
                rule_path = match_rule.group(2).strip()
                is_allow = match_rule.group(1).lower() == "allow"
                for agent in current_agents:
                    rules.setdefault(agent, []).append((rule_path, is_allow))

        agent_rules = rules.get(user_agent) or rules.get("*") or []

        def matches(rule: str, target: str) -> bool:
            """ Retorna ``True`` quando a regra casa com o caminho analisado """
            if not rule:
                return True
            if rule.endswith("$"):
                pattern = re.escape(rule[:-1]).replace(r"\*", ".*") + "$"
            else:
                pattern = re.escape(rule[:-1]).replace(r"\*", ".*")
            return re.match("^" + pattern, target) is not None

        allowed = True
        best_len = -1
        for rule_path, is_allow in agent_rules:
            if matches(rule_path, path):
                rule_len = len(rule_path)
                if rule_len > best_len:
                    best_len = rule_len
                    allowed = is_allow

        if self.redis is not None:
            await asyncio.to_thread(
                self.redis.set,
                cache_rule_key,
                "1" if allowed else "0",
                ex=self.cache_ttl,
            )
        return allowed

class RobotsTxtManager(RobotsTxtParser):
    """ Mantém compatibilidade com o nome legado ``RobotsTxtManager`` """

__all__ = [
    "RobotsTxtManager",
    "RobotsTxtParser",
    "DEFAULT_CACHE_PREFIX",
    "DEFAULT_CACHE_TTL",
    "DEFAULT_REQUEST_TIMEOUT",
]
