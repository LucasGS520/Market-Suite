""" Métricas Prometheus essenciais para o serviço de scraping enxuto.

O módulo concentra apenas contadores, histogramas e gauges efetivamente
utilizados pelo pipeline reduzido. O objetivo é simplificar a
observabilidade mantendo visibilidade sobre sucesso por etapa, latência,
interações com cache e verificações de robots.txt.
"""

from prometheus_client import Counter, Gauge, Histogram


#Métricas focadas no pipeline determinístico do scraper
SCRAPER_TASK_RETRY_ATTEMPTS_TOTAL = Counter(
    "scraper_task_retry_attempts_total",
    "Total de tentativas de retry realizadas pelas tasks de scraping",
    ["task", "reason"],
)

SCRAPER_TASK_RETRY_EXHAUSTED_TOTAL = Counter(
    "scraper_task_retry_exhausted_total",
    "Total de retries esgotados nas tasks de scraping",
    ["task", "reason"],
)

SCRAPER_CIRCUIT_OPEN_EVENTS_TOTAL = Counter(
    "scraper_circuit_open_events_total",
    "Total de bloqueios por circuito aberto ao chamar o scraper",
    ["host"],
)

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

SCRAPER_VALIDATION_REJECT_TOTAL = Counter(
    "scraper_validation_reject_total",
    "Total de rejeições emitidas pelo validador de qualidade",
    ["domain", "step", "reason"],
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

#Contadores específicos do orquestrador de coleta
COLLECTOR_SUCCESS_NEW_DATA_TOTAL = Counter(
    "collector_success_new_data_total",
    "Coletas concluídas com novos dados persistidos",
    ["kind"],
)

COLLECTOR_SUCCESS_NO_CHANGE_TOTAL = Counter(
    "collector_success_no_change_total",
    "Coletas concluídas sem alterações detectadas",
    ["kind"],
)

COLLECTOR_NO_DATA_TOTAL = Counter(
    "collector_no_data_total",
    "Coletas que não retornaram dados utilizáveis",
    ["kind"],
)

COLLECTOR_ERROR_TOTAL = Counter(
    "collector_error_total",
    "Falhas do coletor ao tentar obter dados",
    ["kind"],
)

COLLECTOR_LOCK_ACQUIRED_TOTAL = Counter(
    "collector_lock_acquired_total",
    "Locks adquiridos pelo coletor para evitar paralelismo",
    ["kind"],
)

COLLECTOR_LOCK_SKIPPED_TOTAL = Counter(
    "collector_lock_skipped_total",
    "Execuções ignoradas por lock pré-existente",
    ["kind"],
)

COLLECT_LOCK_SKIPPED_TOTAL = Counter(
    "collect_lock_skipped_total",
    "Coletas ignoradas por lock ativo na entrada da tarefa",
    ["kind"],
)

COLLECT_SUCCESS_TOTAL = Counter(
    "collect_success_total",
    "Coletas concluídas com sucesso e dados utilizáveis",
    ["kind"],
)

#Métricas específicas do ciclo de rechecagem
RECHECK_DISPATCH_TOTAL = Counter(
    "recheck_dispatch_total",
    "Total de monitorados avaliados para rechecagem",
    ["status"],
)

RECHECK_MONITORED_RESULT_TOTAL = Counter(
    "recheck_monitored_result_total",
    "Resultados da coleta do produto monitorado no orquestrador",
    ["result"],
)

RECHECK_COMPETITOR_RESULT_TOTAL = Counter(
    "recheck_competitor_result_total",
    "Resultados das coletas individuais de concorrentes no orquestrador",
    ["result"],
)

RECHECK_ENQUEUED_TOTAL = Counter(
    "recheck_enqueued_total",
    "Monitorados enviados para rechecagem pelo scheduler",
    ["status"],
)

RECHECK_SKIPPED_NO_NEXT_CHECK_TOTAL = Counter(
    "recheck_skipped_no_next_check_total",
    "Monitorados ignorados por ausência de next_check_at",
    ["reason"],
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

SCRAPER_PRICE_PARSER_USAGE_TOTAL = Counter(
    "scraper_price_parser_usage_total",
    "Total de usos do price-parser para interpretar preços por resultado",
    ["outcome"],
)

SCRAPER_DNS_RESOLVE_DURATION_SECONDS = Histogram(
    "scraper_dns_resolve_duration_seconds",
    "Latência para resolver hosts antes de efetuar downloads HTTP",
    ["outcome"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

SCRAPER_DNS_BLOCKED_TOTAL = Counter(
    "scraper_dns_blocked_total",
    "Total de resoluções DNS bloqueadas por motivo de segurança",
    ["reason"],
)

SCRAPER_ROBOTS_CHECK_TOTAL = Counter(
    "scraper_robots_check_total",
    "Total de verificações realizadas contra o robots.txt por resultado",
    ["outcome"],
)

SCRAPER_SINGLEFLIGHT_CALLS_TOTAL = Counter(
    "scraper_singleflight_calls_total",
    "Total de chamadas coordenadas pelo singleflight por papel e resultado",
    ["role", "outcome"],
)

SCRAPER_SINGLEFLIGHT_WAIT_SECONDS = Histogram(
    "scraper_singleflight_wait_seconds",
    "Tempo de espera de participantes singleflight antes de reutilizar o download",
    ["role"],
    buckets=[0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

SCRAPER_HTTP_RETRIES_TOTAL = Counter(
    "scraper_http_retries_total",
    "Total de tentativas extras realizadas durante downloads HTTP do scraper",
    ["target", "reason"],
)

SCRAPER_HTTP_RETRY_BACKOFF_SECONDS = Histogram(
    "scraper_http_retry_backoff_seconds",
    "Tempo de espera aplicado antes de novas tentativas de download HTTP",
    ["target", "reason"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

SCRAPER_HTTP_CLIENT_ERROR_TOTAL = Counter(
    "scraper_http_client_error_total",
    "Total de respostas 4xx observadas durante downloads HTML",
    ["domain", "status"],
)

SCRAPER_HTTP_DECODE_ERROR_TOTAL = Counter(
    "scraper_http_decode_error_total",
    "Total de falhas ao decodificar corpos HTTP baixados pelo scraper",
    ["domain", "encoding", "reason"],
)

SCRAPER_UA_ROTATION_TOTAL = Counter(
    "scraper_ua_rotation_total",
    "Total de User-Agents atribuídos durante o download de HTML",
    ["strategy", "domain"],
)

SCRAPING_SUSPENDED_FLAG = Gauge(
    "scraping_suspended_flag",
    "Flag de suspensão global de scraping controlado via Redis",
)

SCRAPING_SUSPENDED_FLAG.set(0)

__all__ = [
    "SCRAPING_LATENCY_SECONDS",
    "SCRAPER_IN_FLIGHT",
    "SCRAPER_HEAD_FAILURES_TOTAL",
    "SCRAPER_TASK_RETRY_ATTEMPTS_TOTAL",
    "SCRAPER_TASK_RETRY_EXHAUSTED_TOTAL",
    "SCRAPER_CIRCUIT_OPEN_EVENTS_TOTAL",
    "SCRAPER_CACHE_LOOKUPS_TOTAL",
    "SCRAPER_CACHE_SIZE",
    "SCRAPER_CACHE_EVICTIONS_TOTAL",
    "SCRAPER_CACHE_HIT_RATE",
    "SCRAPER_PRICE_PARSER_USAGE_TOTAL",
    "SCRAPER_DNS_RESOLVE_DURATION_SECONDS",
    "SCRAPER_DNS_BLOCKED_TOTAL",
    "SCRAPER_ROBOTS_CHECK_TOTAL",
    "SCRAPER_SINGLEFLIGHT_CALLS_TOTAL",
    "SCRAPER_SINGLEFLIGHT_WAIT_SECONDS",
    "SCRAPER_HTTP_RETRIES_TOTAL",
    "SCRAPER_HTTP_RETRY_BACKOFF_SECONDS",
    "SCRAPER_HTTP_CLIENT_ERROR_TOTAL",
    "SCRAPER_HTTP_DECODE_ERROR_TOTAL",
    "SCRAPER_UA_ROTATION_TOTAL",
    "SCRAPING_SUSPENDED_FLAG",
    "SCRAPER_STEP_SUCCESS_TOTAL",
    "SCRAPER_STEP_LATENCY_SECONDS",
    "SCRAPER_STEP_FALLBACK_TOTAL",
    "SCRAPER_STEP_INVALID_TOTAL",
    "SCRAPER_VALIDATION_REJECT_TOTAL",
    "SCRAPER_NO_RESULT_TOTAL",
    "COLLECTOR_SUCCESS_NEW_DATA_TOTAL",
    "COLLECTOR_SUCCESS_NO_CHANGE_TOTAL",
    "COLLECTOR_NO_DATA_TOTAL",
    "COLLECTOR_ERROR_TOTAL",
    "COLLECTOR_LOCK_ACQUIRED_TOTAL",
    "COLLECTOR_LOCK_SKIPPED_TOTAL",
    "COLLECT_LOCK_SKIPPED_TOTAL",
    "COLLECT_SUCCESS_TOTAL",
    "RECHECK_DISPATCH_TOTAL",
    "RECHECK_MONITORED_RESULT_TOTAL",
    "RECHECK_COMPETITOR_RESULT_TOTAL",
    "RECHECK_ENQUEUED_TOTAL",
    "RECHECK_SKIPPED_NO_NEXT_CHECK_TOTAL",
]
