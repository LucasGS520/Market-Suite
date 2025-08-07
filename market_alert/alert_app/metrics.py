"""Definições de métricas do MarketAlert

Este módulo centraliza todas as métricas Prometheus utilizadas
pela aplicação e as organiza por domínio.
Os principais Grupos cobertos são:
- Tarefas e workers do Celery
- Scraping de produtos e comportamento HTTP relacionado
- Cache e uso de cache por endpoint
- Auditoria de logs
- Eventos de autenticação
- Rotinas de comparação de preços
- Interações com o servidor HTTP do FastAPI
- Estado do pool de conexões com o banco de dados
- Parsing e agendamentos adaptativos de rechecagem
- Contadores de logs e erros de API
- Estatísticas de filas e memória do Redis

Cada seção neste arquivo é precedida por um cabeçalho de comentário,
garantindo que as métricas permaneçam fáceis de localizar e manter
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------- CELERY METRICS ----------
CELERY_TASKS_TOTAL = Counter(
    "celery_tasks_total",
    "Total de tarefas executadas pelo Celery",
    ["task_name", "status"], #Labels para nome de task e status (success/failure)
)

#Métrica do tamanho das filas do Celery (pending tasks)
CELERY_QUEUE_LENGTH = Gauge(
    "celery_queue_length",
    "Número de tarefas pendentes na fila Celery",
    ["queue"]
)

#Métrica total de workers e concorrência
CELERY_WORKERS_TOTAL = Gauge(
    "celery_workers_total",
    "Total de workers Celery ativos",
)

CELERY_WORKER_CONCURRENCY = Gauge(
    "celery_worker_concurrency",
    "Grau de concorrência configurado nos workers Celery",
)

CELERY_TASK_DURATION_SECONDS = Histogram(
    "celery_task_duration_seconds",
    "Tempo de execução de cada tarefa celery (segundos)",
    ["task_name"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)


# ---------- SCRAPING METRICS ----------
#Latência das operações de scraping (em segundos)
SCRAPING_LATENCY_SECONDS = Histogram(
    "scraping_latency_seconds",
    "Tempo gasto em scraping de produto (segundos)",
    ["source"], #ex: 'api', 'monitor_scrape', 'monitor_competitor', 'scraper'
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
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
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
    "Total de vezes que o scraper recorreu para o BrowserManager em modo headless",
)

SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL = Counter(
    "scraper_browser_recovery_success_total",
    "Total de recuperações bem-sucedidas via navegador Playwright",
)

#Tamanho das requisições HTTP enviadas pelo scraper (bytes)
SCRAPER_REQUEST_SIZE_BYTES = Histogram(
    "scraper_request_size_bytes",
    "Distribuição do tamanho das requisições HTTP do scraper (bytes)",
    ["method"],
    buckets=[128, 512, 1024, 4096, 16384, 65536, 262144],
)

#Tamanho das respostas HTTP recebidas pelo scraper (bytes)
SCRAPER_RESPONSE_SIZE_BYTES = Histogram(
    "scraper_response_size_bytes",
    "Distribuição do tamanho das respostas HTTP do scraper (bytes)",
    ["method", "status_code"],
    buckets=[128, 512, 1024, 4096, 16384, 65536, 262144],
)

#Contagem de sucessos e falhas por URL acessada
SCRAPER_URL_STATUS_TOTAL = Counter(
    "scraper_url_status_total",
    "Total de requisições por domínio de URL e status de sucesso ou falha",
    ["url_host", "status"],
)

#Contador de mudanças no estado do circuit breaker
SCRAPER_CIRCUIT_STATE_CHANGES_TOTAL = Counter(
    "scraper_circuit_state_changes_total",
    "Total de mudanças de estado do circuit breaker do scraper",
    ["state"],
)


# ---------- CACHE METRICS ----------
CACHE_HITS_TOTAL = Counter(
    "cache_hits_total",
    "Total de acessos ao cache que retornaram dados",
)

CACHE_MISSES_TOTAL = Counter(
    "cache_misses_total",
    "Total de acessos ao cache sem dados disponíveis",
)


# ---------- CACHE PER ENDPOINT METRICS ----------
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


# ---------- AUDIT LOG METRICS ----------
#Métricas para auditoria de logs
AUDIT_RECORDS_TOTAL = Counter(
    "audit_records_total",
    "Total de registros de auditoria gerados",
    ["stage"]
)

AUDIT_HTML_LENGTH_BYTES = Histogram(
    "audit_html_length_bytes",
    "Tamanho em bytes do HTML registrado na auditoria",
    ["stage"],
    buckets=[0, 256, 1024, 4096, 16384, 65536, 262144],
)

AUDIT_RECORD_DURATION_SECONDS = Histogram(
    "audit_record_duration_seconds",
    "Tempo gasto para gravar cada registro de auditoria (segundos)",
    ["stage"],
    buckets=[0.0001, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

AUDIT_ERRORS_TOTAL = Counter(
    "audit_errors_total",
    "Total de erros ao gravar registros de auditoria",
    ["stage"],
)


# ---------- AUTHENTICATION METRICS ----------
#Métricas de erros de login/autenticação
LOGIN_ERRORS_TOTAL = Counter(
    "login_errors_total",
    "Total de erros de autenticação",
    ["reason"], #ex: invalid_credentials, token_expired
)


# ---------- PRICE COMPARISON METRICS ----------
#Total de execuções do método de comparação de preços
PRICE_COMPARISONS_TOTAL = Counter(
    "price_comparisons_total",
    "Total de execuções de comparação de preços",
    ["status"], #success ou failure
)

#Duração da comparação de preços em segundos
PRICE_COMPARISON_DURATION_SECONDS = Histogram(
    "price_comparison_duration_seconds",
    "Tempo de execução da comparação de preços (segundos)",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0],
)

#Contagem de alertas gerados nas comparações
PRICE_ALERTS_TOTAL = Counter(
    "price_alerts_total",
    "Total de alertas de preço gerados",
)


# ---------- HTTP SERVER (FASTAPI) METRICS ----------
#Contador de requisições HTTP recebidas
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Contador de requisições HTTP recebidas",
    ["method", "endpoint", "status_code"],
)

#Latência de respostas HTTP (em segundos)
HTTP_REQUESTS_LATENCY_SECONDS = Histogram(
    "http_request_latency_seconds",
    "Tempo de resposta das requisições HTTP",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ---------- DATABASE (SQLALCHEMY) METRICS ----------
#Tamanho do pool de conexões
DB_POOL_SIZE = Gauge(
    "db_pool_size",
    "Tamanho do pool de conexões do banco de dados",
)

#Conexões ativas atualmente em uso
DB_POOL_CHECKOUTS = Gauge(
    "db_pool_checkouts",
    "Número de conexões ativas no pool de banco de dados",
)


# ---------- PARSER METRICS ----------
PARSER_SUCCESS_TOTAL = Counter(
    "parser_success_total",
    "Total de registros de produtos parseados com sucesso",
)

PARSER_FAILURE_TOTAL = Counter(
    "parser_failure_total",
    "Total de falhas ao parser registros de produtos",
)


# ---------- ADAPTIVE RECHECK METRICS ----------
RECHECK_SCHEDULED_TOTAL = Counter(
    "recheck_scheduled_total",
    "Total de rechecks agendados",
)


# ---------- LOGGING METRICS ----------
LOG_ENTRIES_TOTAL = Counter(
    "log_entries_total",
    "Total de linhas de log geradas",
    ["level"],
)


# ---------- API ERROR METRICS ----------
API_ERRORS_TOTAL = Counter(
    "api_errors_total",
    "Total de respostas com erro da API",
    ["endpoint", "status_code"],
)


# ---------- REDIS METRICS ----------
REDIS_QUEUE_MESSAGES = Gauge(
    "redis_queue_messages",
    "Total de mensagens pendentes em filas Redis",
    ["queue"],
)

REDIS_MEMORY_USAGE_BYTES = Gauge(
    "redis_memory_usage_bytes",
    "Uso de memória pelo Redis em bytes",
)


# ---------- ALERT RULES METRICS ----------
ALERT_RULES_TRIGGERED_TOTAL = Counter(
    "alert_rules_triggered_total",
    "Total de vezes que uma regra de alerta foi acionada",
    ["rule_type"],
)

ALERT_RULES_SUPPRESSED_TOTAL = Counter(
    "alert_rules_suppressed_total",
    "Alertas suprimidos por cooldown ou duplicidade",
    ["reason"]
)

ALERT_RULES_ACTIVE = Gauge(
    "alert_rules_active",
    "Número de regras de alerta ativas no sistema"
)

# ---------- NOTIFICATION METRICS ----------
#Contador de envios de notificações
NOTIFICATIONS_SENT_TOTAL = Counter(
    "notifications_sent_total",
    "Total de notificações enviadas",
    ["channel", "success"],
)

#Contador de notificações ignoradas por motivo
NOTIFICATIONS_SKIPPED_TOTAL = Counter(
    "notifications_skipped_total",
    "Total de notificações não enviadas",
    ["reason"]
)

#Duração do envio de notificações em segundos
NOTIFICATION_SEND_DURATION_SECONDS = Histogram(
    "notification_send_duration_seconds",
    "Tempo de envio de notificações (segundos)",
    ["channel"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0]
)
