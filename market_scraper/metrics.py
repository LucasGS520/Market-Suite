""" Definição de métricas Prometheus usadas pelo serviço de scraping """

from prometheus_client import Counter, Histogram, Gauge

from market_alert.metrics import SCRAPER_BROWSER_FALLBACK_TOTAL, SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL, \
    PARSER_SUCCESS_TOTAL, PARSER_FAILURE_TOTAL, SCRAPER_JITTER_SECONDS, SCRAPER_BACKOFF_FACTOR

#Contador de requisições HTTP do scraper
SCRAPER_REQUESTS_TOTAL = Counter(
    "scraper_requests_total",
    "Total de requisições HTTP feitas pelo scraper",
    ["method", "status_code"],
)

#Tamanho das respostas HTTP recebidas
SCRAPER_RESPONSE_SIZE_BYTES = Histogram(
    "scraper_response_size_bytes",
    "Distribuição do tamanho das respostas HTTP do scraper (bytes)",
    ["method", "status_code"],
    buckets=[128, 512, 1024, 4096, 16384, 65536, 262144],
)

#Contador de sucesso/erro por domínio acessado
SCRAPER_URL_STATUS_TOTAL = Counter(
    "scraper_url_status_total",
    "Total de requisições por domínio de URL e status de sucesso ou falha",
    ["url_host", "status"],
)

#Número de respostas bloqueadas (403/429)
SCRAPER_HTTP_BLOCKED_TOTAL = Counter(
    "scraper_http_blocked_total",
    "Total de respostas bloqueadas (status 403/429) recebidas pelo scraper",
)

#Total de captchas detectados
SCRAPER_CAPTCHA_TOTAL = Counter(
    "scraper_captcha_total",
    "Total de captchas detectados pelo scraper",
)

#Total de quedas para Playwright ao falhar requisições HTTP
SCRAPER_BROWSER_FALLBACK_TOTAL = Counter(
    "scraper_browser_fallback_total",
    "Total de tentativas em que o Playwright precisou ser acionado",
)

#Sucesso na recuperação de bloqueios utilizando navegador real
SCRAPER_BROWSER_RECOVERY_SUCCESS_TOTAL = Counter(
    "scraper_browser_recovery_success_total",
    "Número de vezes que o navegador recuperou o acesso após bloqueio",
)

#Sucessos e falhas do parser de HTML
PARSER_SUCCESS_TOTAL = Counter(
    "parser_success_total",
    "Total de execuções bem-sucedidas do parser",
)

PARSER_FAILURE_TOTAL = Counter(
    "parser_failure_total",
    "Total de falhas na extração de dados pelo parser",
)

#Observa jitter aplicado entre as requisições
SCRAPER_JITTER_SECONDS = Histogram(
    "scraper_jitter_seconds",
    "Distribuição dos valores de jitter aplicados nas requisições",
)

#Fator de backoff usado pelo throttle
SCRAPER_BACKOFF_FACTOR = Gauge(
    "scraper_backoff_factor",
    "Fator de redução atual aplicado pelo throttle de scraping",
)
