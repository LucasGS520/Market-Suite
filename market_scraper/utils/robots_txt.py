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
