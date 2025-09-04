""" Métricas prometheus relacionadas ao processo de scraping

Inclui contadores e gauges para monitorar requisições, latência,
bloqueios e mecanismos de fallback, oferecendo visibilidade
completa sobre o comportamento do scraper.
"""

from prometheus_client import Counter, Gauge, Histogram


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

SCRAPER_REQUESTS_TOTAL = Counter(
    "scraper_requests_total",
    "Total de requisições HTTP feitas pelo scraper",
    ["method", "status_code"],
)

SCRAPER_HEAD_FAILURES_TOTAL = Counter(
    "scraper_head_failures_total",
    "Total de falhas de scraping registradas",
)

SCRAPER_HTTP_BLOCKED_TOTAL = Counter(
    "scraper_http_blocked_total",
    "Total de respostas bloqueadas (status 403/429) recebidas pelo scraper",
)

SCRAPER_JITTER_SECONDS = Histogram(
    "scraper_jitter_seconds",
    "Distribuição dos atrasos de jitter aplicados pelo ThrottleManager (segundos)",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

SCRAPER_BACKOFF_FACTOR = Gauge(
    "scraper_backoff_factor",
    "Fator de backoff/exponenciação atual usado pelo ThrottleManager",
)

SCRAPER_CIRCUIT_OPEN = Gauge(
    "scraper_circuit_open",
    "Estado atual do circuit breaker do scraper",
    ["state"],
)

SCRAPING_SUSPENDED_FLAG = Gauge(
    "scraping_suspended_flag",
    "Flag de suspensão global de scraping",
)

SCRAPER_CIRCUIT_OPEN.labels(state="open").set(0)
SCRAPER_CIRCUIT_OPEN.labels(state="closed").set(1)
SCRAPING_SUSPENDED_FLAG.set(0)

SCRAPER_RETRY_TOTAL = Counter(
    "scraper_retry_total",
    "Total de tentativas de retry feitas pelo scraper",
)

SCRAPER_CAPTCHA_TOTAL = Counter(
    "scraper_captcha_total",
    "Total de captchas detectados pelo scraper",
)

SCRAPER_BROWSER_FALLBACK_TOTAL = Counter(
    "scraper_browser_fallback_total",
    "Total de vezes que o scraper recorreu a um navegador headless",
)

SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL = Counter(
    "scraper_browser_recovery_success_total",
    "Total de recuperações bem-sucedidas via navegador headless",
)

SCRAPER_STRATEGY_TOTAL = Counter(
    "scraper_strategy_total",
    "Total de execuções por estratégia de scraping",
    ["strategy", "status"],
)

SCRAPER_FALLBACK_TOTAL = Counter(
    "scraper_fallback_total",
    "Total de fallbacks acionados entre estratégias após falha de validação de dados",
)

SCRAPER_REQUEST_SIZE_BYTES = Histogram(
    "scraper_request_size_bytes",
    "Distribuição do tamanho das requisições HTTP do scraper (bytes)",
    ["method"],
    buckets=[128, 512, 1024, 4096, 16384, 65536, 262144],
)

SCRAPER_RESPONSE_SIZE_BYTES = Histogram(
    "scraper_response_size_bytes",
    "Distribuição do tamanho das respostas HTTP do scraper (bytes)",
    ["method", "status_code"],
    buckets=[128, 512, 1024, 4096, 16384, 65536, 262144],
)

SCRAPER_URL_STATUS_TOTAL = Counter(
    "scraper_url_status_total",
    "Total de requisições por domínio de URL e status de sucesso ou falha",
    ["url_host", "status"],
)

SCRAPER_CIRCUIT_STATE_CHANGES_TOTAL = Counter(
    "scraper_circuit_state_changes_total",
    "Total de mudanças de estado do circuit breaker do scraper",
    ["state"],
)

__all__ = [
    "SCRAPING_LATENCY_SECONDS",
    "SCRAPER_IN_FLIGHT",
    "SCRAPER_REQUESTS_TOTAL",
    "SCRAPER_HEAD_FAILURES_TOTAL",
    "SCRAPER_HTTP_BLOCKED_TOTAL",
    "SCRAPER_JITTER_SECONDS",
    "SCRAPER_BACKOFF_FACTOR",
    "SCRAPER_CIRCUIT_OPEN",
    "SCRAPING_SUSPENDED_FLAG",
    "SCRAPER_RETRY_TOTAL",
    "SCRAPER_CAPTCHA_TOTAL",
    "SCRAPER_BROWSER_FALLBACK_TOTAL",
    "SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL",
    "SCRAPER_STRATEGY_TOTAL",
    "SCRAPER_FALLBACK_TOTAL",
    "SCRAPER_REQUEST_SIZE_BYTES",
    "SCRAPER_RESPONSE_SIZE_BYTES",
    "SCRAPER_URL_STATUS_TOTAL",
    "SCRAPER_CIRCUIT_STATE_CHANGES_TOTAL",
]
