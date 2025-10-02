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
    "Distribuição dos atrasos de jitter aplicados pelo controlador de ritmo (segundos)",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

SCRAPER_BACKOFF_FACTOR = Gauge(
    "scraper_backoff_factor",
    "Fator de backoff/exponenciação atual usado pelo controlador de ritmo",
)

SCRAPER_CIRCUIT_STATE = Gauge(
    "scraper_circuit_state",
    "Estado atual do circuit breaker do scraper por domínio",
    ["host", "state"],
)

SCRAPER_CIRCUIT_TRANSITIONS_TOTAL = Counter(
    "scraper_circuit_transitions_total",
    "Total de mudanças de estado do circuit breaker do scraper por domínio",
    ["host", "state"],
)

SCRAPER_CIRCUIT_ATTEMPTS_TOTAL = Counter(
    "scraper_circuit_attempts_total",
    "Total de tentativas observadas pelo circuit breaker (permitidas, bloqueadas e falhas)",
    ["host", "result"],
)

SCRAPER_CIRCUIT_SUSPENSIONS_TOTAL = Counter(
    "scraper_circuit_suspensions_total",
    "Total de suspensões aplicadas pelo circuit breaker por nível de severidade",
    ["host", "level"],
)

SCRAPING_SUSPENDED_FLAG = Gauge(
    "scraping_suspended_flag",
    "Flag de suspensão global de scraping",
)

SCRAPING_SUSPENDED_FLAG.set(0)

SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS = Gauge(
    "scraper_domain_policy_last_load_success",
    "Indica se a última carga do domain_policy.yaml foi bem-sucedida (1) ou falhou (0)",
)

SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS.set(1)

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

SCRAPER_FEATURE_FLAG_TOTAL = Counter(
    "scraper_feature_flag_total",
    "Total de decisões tomadas por feature flags no fluxo de scraping",
    ["feature", "state"],
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

SCRAPER_RATE_LIMIT_REQUESTS_TOTAL = Counter(
    "scraper_rate_limit_requests_total",
    "Total de verificações realizadas pelo limitador de taxa do scraper",
    ["host", "result"],
)

SCRAPER_RATE_LIMIT_LATENCY_SECONDS = Histogram(
    "scraper_rate_limit_latency_seconds",
    "Latência das verificações do limitador de taxa do scraper (segundos)",
    ["host"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

SCRAPER_RATE_LIMIT_MODE = Gauge(
    "scraper_rate_limit_mode",
    "Modo atual do limitador de taxa (1=ativo via Redis, 0=passivo sem Redis)",
    ["host"],
)

SCRAPER_CACHE_LOOKUPS_TOTAL = Counter(
    "scraper_cache_lookups_total",
    "Total de consultas ao cache inteligente do scraper",
    ["backend", "outcome"],
)

SCRAPER_CACHE_LATENCY_SECONDS = Histogram(
    "scraper_cache_latency_seconds",
    "Latência das operações do cache inteligente do scraper (segundos)",
    ["operation"],
    buckets=[0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)

SCRAPER_CACHE_LOCAL_SIZE = Gauge(
    "scraper_cache_local_size",
    "Quantidade de entradas armazenadas no cache local de contingência do scraper",
)

SCRAPER_CACHE_LOCK_TOTAL = Counter(
    "scraper_cache_lock_total",
    "Total de tentativas de lock distribuído realizadas pelo cache do scraper",
    ["outcome"],
)


__all__ = [
    "SCRAPING_LATENCY_SECONDS",
    "SCRAPER_IN_FLIGHT",
    "SCRAPER_REQUESTS_TOTAL",
    "SCRAPER_HEAD_FAILURES_TOTAL",
    "SCRAPER_HTTP_BLOCKED_TOTAL",
    "SCRAPER_JITTER_SECONDS",
    "SCRAPER_BACKOFF_FACTOR",
    "SCRAPER_CIRCUIT_STATE",
    "SCRAPER_CIRCUIT_TRANSITIONS_TOTAL",
    "SCRAPER_CIRCUIT_ATTEMPTS_TOTAL",
    "SCRAPER_CIRCUIT_SUSPENSIONS_TOTAL",
    "SCRAPING_SUSPENDED_FLAG",
    "SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS",
    "SCRAPER_RETRY_TOTAL",
    "SCRAPER_CAPTCHA_TOTAL",
    "SCRAPER_BROWSER_FALLBACK_TOTAL",
    "SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL",
    "SCRAPER_STRATEGY_TOTAL",
    "SCRAPER_FALLBACK_TOTAL",
    "SCRAPER_FEATURE_FLAG_TOTAL",
    "SCRAPER_REQUEST_SIZE_BYTES",
    "SCRAPER_RESPONSE_SIZE_BYTES",
    "SCRAPER_URL_STATUS_TOTAL",
    "SCRAPER_RATE_LIMIT_REQUESTS_TOTAL",
    "SCRAPER_RATE_LIMIT_LATENCY_SECONDS",
    "SCRAPER_RATE_LIMIT_MODE",
    "SCRAPER_CACHE_LOOKUPS_TOTAL",
    "SCRAPER_CACHE_LATENCY_SECONDS",
    "SCRAPER_CACHE_LOCAL_SIZE",
    "SCRAPER_CACHE_LOCK_TOTAL",
]
