""" Configurações especializadas para o utilitário de leitura de robots.txt 

O objetivo é centralizar parâmetros como prefixo de cache, tempo de vida e
timeout de requisições para que o parser opere com valores consistentes em
toda a aplicação. O design segue a mesma abordagem dos demais utilitários,
favorecendo a substituição posterior por soluções externas caso desejado.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Lock
from typing import Optional

from market_scraper.core.config_scraper import settings as scraper_settings


__all__ = ["RobotsConfig", "RobotsSettings", "settings"]

@dataclass(frozen=True)
class RobotsConfig:
    """ Agrupa parâmetros utilizados pelo ``RobotsTxtParser`` """
    cache_key_prefix: str
    cache_ttl: int
    request_timeout: int

class RobotsSettings:
    """ Gerencia a configuração atual do parser de ``robots.txt`` """
    def __init__(self, initial: Optional[RobotsConfig] = None) -> None:
        self._lock = Lock()
        self._config = initial or RobotsConfig(
            cache_key_prefix=scraper_settings.ROBOTS_CACHE_KEY,
            cache_ttl=int(scraper_settings.ROBOTS_CACHE_TTL),
            request_timeout=5,
        )

    def current(self) -> RobotsConfig:
        """ Retorna configuração vigente de forma imutável """
        with self._lock:
            return self._config
        
    def update(
        self,
        *,
        cache_key_prefix: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        request_timeout: Optional[int] = None,
    ) -> RobotsConfig:
        """ Atualiza campos definidos e devolve a nova configuração """
        with self._lock:
            config = self._config
            if cache_key_prefix is not None:
                config = replace(config, cache_key_prefix=cache_key_prefix)
            if cache_ttl is not None:
                config = replace(config, cache_ttl=int(cache_ttl))
            if request_timeout is not None:
                config = replace(config, request_timeout=int(request_timeout))
            self._config = config
            return config
        
#Instância global utilizada pelos utilitários
settings = RobotsSettings()
