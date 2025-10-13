""" Métricas Prometheus essenciais para o serviço de scraping enxuto.

O módulo concentra apenas contadores, histogramas e gauges efetivamente
utilizados pelo pipeline reduzido. O objetivo é simplificar a
observabilidade mantendo visibilidade sobre sucesso por etapa, latência,
interações com cache e verificações de robots.txt.
"""

from prometheus_client import Counter, Gauge, Histogram


#Métricas focadas no pipeline determinístico do scraper
SCRAPER_STEP_SUCCESS_TOTAL = Counter(
    "scraper_step_success_total",
    "Total de execuções bem-sucedidas por etapa do pipeline do scraper",
    ["step", "domain", "result"],
)

SCRAPER_STEP_LATENCY_SECONDS = Histogram(
    "scraper_step_latency_seconds",
    "Latência das etapas do pipeline do scraper (segundos)",
    ["step", "domain", "result"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

SCRAPER_STEP_FALLBACK_TOTAL = Counter(
    "scraper_step_fallback_total",
    "Total de vezes que uma etapa precisou recorrer ao fallback",
    ["step", "domain", "result"],
)

SCRAPER_STEP_INVALID_TOTAL = Counter(
    "scraper_step_invalid_total",
    "Total de resultados descartados por invalidação de qualidade",
    ["step", "domain", "result"],
)

SCRAPER_NO_RESULT_TOTAL = Counter(
    "scraper_no_result_total",
    "Execuções que não retornaram um payload válido ao final do pipeline",
    ["domain", "result"],
)

SCRAPING_LATENCY_SECONDS = Histogram(
    "scraping_latency_seconds",
    "Tempo gasto em scraping de produto (segundos)",
    ["source"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

SCRAPER_IN_FLIGHT = Gauge(
    "scraper_in_flight_requests",
    "Número de requisições de scraping em andamento",
)

SCRAPER_HEAD_FAILURES_TOTAL = Counter(
    "scraper_head_failures_total",
    "Total de falhas de scraping registradas",
)

SCRAPER_CACHE_LOOKUPS_TOTAL = Counter(
    "scraper_cache_lookups_total",
    "Total de consultas ao cache básico do scraper por resultado",
    ["outcome"],
)

SCRAPER_CACHE_SIZE = Gauge(
    "scraper_cache_size",
    "Quantidade de entradas ativas no cache básico do scraper",
)

SCRAPER_CACHE_EVICTIONS_TOTAL = Counter(
    "scraper_cache_evictions_total",
    "Total de itens removidos do cache básico do scraper por motivo",
    ["reason"],
)

SCRAPER_CACHE_HIT_RATE = Gauge(
    "scraper_cache_hit_rate",
    "Taxa de acerto observada no cache básico do scraper",
)

SCRAPER_ROBOTS_CHECK_TOTAL = Counter(
    "scraper_robots_check_total",
    "Total de verificações realizadas contra o robots.txt por resultado",
    ["outcome"],
)

SCRAPING_SUSPENDED_FLAG = Gauge(
    "scraping_suspended_flag",
    "Flag de suspensão global de scraping controlado via Redis",
)

SCRAPING_SUSPENDED_FLAG.set(0)

SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS = Gauge(
    "scraper_domain_policy_last_load_success",
    "Estado da última tentativa de carregar políticas por domínio",
)

SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS.set(1)


__all__ = [
    "SCRAPING_LATENCY_SECONDS",
    "SCRAPER_IN_FLIGHT",
    "SCRAPER_HEAD_FAILURES_TOTAL",
    "SCRAPER_CACHE_LOOKUPS_TOTAL",
    "SCRAPER_CACHE_SIZE",
    "SCRAPER_CACHE_EVICTIONS_TOTAL",
    "SCRAPER_CACHE_HIT_RATE",
    "SCRAPER_ROBOTS_CHECK_TOTAL",
    "SCRAPING_SUSPENDED_FLAG",
    "SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS",
    "SCRAPER_STEP_SUCCESS_TOTAL",
    "SCRAPER_STEP_LATENCY_SECONDS",
    "SCRAPER_STEP_FALLBACK_TOTAL",
    "SCRAPER_STEP_INVALID_TOTAL",
    "SCRAPER_NO_RESULT_TOTAL",
]
