""" Gerencia o cache inteligente de produtos com TTL adaptativo.

Este módulo armazena em Redis os dados extraídos, um hash do HTML
e o ETag relacionado. Quando o mesmo conteúdo é visto repetidamente
o TTL é aumentado, reduzindo novas requisições de scraping.
"""

import json
import hashlib
from typing import Optional

from utils.redis_client import get_redis_client
from scraper_app.core.config import settings


class IntelligentCacheManager:
    """ Cache de produtos com TTL adaptativo baseado no conteúdo """

    def __init__(self, base_ttl: int = settings.CACHE_BASE_TTL, max_multiplier: int = 5) -> None:
        """ Inicializa o gerenciador definindo TTL base e multiplicador máximo """
        self.redis = get_redis_client()
        self.base_ttl = base_ttl
        self.max_multiplier = max_multiplier

    def _key(self, url: str) -> str:
        """ Retorna a chave Redis utilizada para a URL. """
        return f"cache:product:{url}"

    def _hash_content(self, content: str) -> str:
        """ Gera hash SHA-256 do HTML para identificar alterações """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get(self, url: str) -> Optional[dict]:
        """ Recupera a entrada completa do cache ou ``None`` caso ausente """
        raw = self.redis.get(self._key(url))
        if not raw:
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return None

    def get_data(self, url: str) -> Optional[dict]:
        """ Retorna apenas o campo ``data`` salvo para a URL """
        entry = self.get(url)
        return entry.get("data") if entry else None

    def set(self, url: str, data: dict, content: str, etag: Optional[str] = None) -> None:
        """ Armazena dados e HTML no cache ajustando o TTL conforme o conteúdo """
        key = self._key(url)
        content_hash = self._hash_content(content)
        existing = self.get(url)
        multiplier = 1

        #Se o conteúdo não mudou, aumenta o multiplicador para ampliar o TTL
        if existing:
            if content_hash == existing.get("hash"):
                multiplier = min(existing.get("multiplier", 1) + 1, self.max_multiplier)
            else:
                multiplier = 1

        ttl = self.base_ttl * multiplier #TTL adaptativo
        entry = {
            "data": data,
            "hash": content_hash,
            "etag": etag,
            "multiplier": multiplier
        }
        self.redis.set(key, json.dumps(entry), ex=ttl)

    def invalidate(self, url: str) -> None:
        """ Remove a entrada de cache da URL informada """
        self.redis.delete(self._key(url))

    def cleanup(self) -> int:
        """ Remove entradas persistentes ou expiradas manualmente e retorna a quantidade de chaves removidas """
        removed = 0
        for key in self.redis.scan_iter(match="cache:product:*"):
            ttl = self.redis.ttl(key)
            if ttl == -1:
                self.redis.delete(key)
                removed += 1
        return removed

