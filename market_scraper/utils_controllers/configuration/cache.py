""" Loader de configuração do cache inteligente do Market Scraper 

O módulo encapsula a leitura dos parâmetros de cache (prefixo e tempos de
vida) em uma estrutura imutável para simplificar o compartilhamento entre
utilitários. A abordagem evita dependências direta de variáveis de ambiente
nas camadas de serviço e facilita eventuais trocas da implementação de 
cache no futuro.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Lock
from typing import Optional

from market_scraper.core.config_scraper import settings as scraper_settings


__all__ = ["CacheConfig", "CacheSettings", "settings"]

@dataclass(frozen=True)
class CacheConfig:
    """ Agrupa parâmetros essenciais utilizados pelo ``IntelligentCacheManager`` """
    prefix: str
    ttl: int
    etag_ttl: int
    signature_ttl: int

class CacheSettings:
    """ Mantém a confuguração atual do cache com sincronização de acesso """
    def __init__(self, initial: Optional[CacheConfig] = None) -> None:
        self._lock = Lock()
        self._config = initial or CacheConfig(
            prefix="scraper:product:",
            ttl=int(scraper_settings.CACHE_BASE_TTL),
            etag_ttl=int(scraper_settings.ETAG_CACHE_TTL),
            signature_ttl=int(scraper_settings.SIG_CACHE_TTL),
        )

    def current(self) -> CacheConfig:
        """ Retorna uma cópia imutável da configuração em uso """
        with self._lock:
            return self._config
        
    def update(
        self,
        *,
        prefix: Optional[str] = None,
        ttl: Optional[int] = None,
        etag_ttl: Optional[int] = None,
        signature_ttl: Optional[int] = None,
    ) -> CacheConfig:
        """ Atualiza os parâmetros de cache retornando a nova estrutura """
        with self._lock:
            config = self._config
            if prefix is not None:
                config = replace(config, prefix=prefix)
            if ttl is not None:
                config = replace(config, ttl=int(ttl))
            if etag_ttl is not None:
                config = replace(config, etag_ttl=int(etag_ttl))
            if signature_ttl is not None:
                config = replace(config, signature_ttl=int(signature_ttl))
            self._config = config
            return config
        
#Instância padrão utilizada pelos utilitários
settings = CacheSettings()
