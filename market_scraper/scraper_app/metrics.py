""" Definição de métricas Prometheus usadas pelo serviço de scraping """

from prometheus_client import Counter, Histogram


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
