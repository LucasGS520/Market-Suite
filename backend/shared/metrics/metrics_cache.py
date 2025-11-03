""" Métricas Prometheus relativas ao uso de cache

Abrange acertos, falhas e limpeza de entradas tanto
de forma geral quanto por endpoint específico.
"""

from prometheus_client import Counter

CACHE_HITS_TOTAL = Counter(
    "cache_hits_total",
    "Total de acessos cache que retornaram dados",
)

CACHE_MISSES_TOTAL = Counter(
    "cache_misses_total",
    "Total de acessos ao cache sem dados disponíveis",
)

CACHE_HITS_ENDPOINT_TOTAL = Counter(
    "cache_hits_endpoint_total",
    "Total de hits de cache por endpoint",
    ["endpoint"],
)

CACHE_MISSES_ENDPOINT_TOTAL = Counter(
    "cache_misses_endpoint_total",
    "Total de misses de cache por endpoint",
    ["endpoint"],
)

CACHE_CLEANUP_TOTAL = Counter(
    "cache_cleanup_total",
    "Total de entradas removidas do cache de scraping",
)

__all__ = [
    "CACHE_HITS_TOTAL",
    "CACHE_MISSES_TOTAL",
    "CACHE_HITS_ENDPOINT_TOTAL",
    "CACHE_MISSES_ENDPOINT_TOTAL",
    "CACHE_CLEANUP_TOTAL",
]
