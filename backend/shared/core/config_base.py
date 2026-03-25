""" Define parâmetros de configuração compartilhados entre os serviços

Este módulo centraliza variáveis de ambiente usadas tanto pelo
`market_alert` quanto pelo `market_scraper`, servindo como base para as
configurações específicas de cada serviço.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


#Diretório base do projeto (raiz do repositório)
BASE_DIR = Path(__file__).resolve().parents[2]

#Nome do serviço que está sendo executado
SERVICE_NAME = os.getenv("SERVICE_NAME")

#Carrega primeiro as variáveis comuns a todos os serviços
common_env = BASE_DIR / ".env.common"
load_dotenv(common_env, override=False)

if SERVICE_NAME:
    #Arquivo específico do serviço atual
    ENV_FILE = BASE_DIR / f".env.{SERVICE_NAME}"
    load_dotenv(ENV_FILE, override=True)
else:
    #Retrocompatibilidade: utiliza ``ENV_FILE`` ou ``.env``
    ENV_FILE = Path(os.getenv("ENV_FILE", ".env"))
    if not ENV_FILE.is_absolute():
        ENV_FILE = BASE_DIR / ENV_FILE
    load_dotenv(ENV_FILE, override=True)

__all__ = ["ConfigBase"]


class ConfigBase(BaseSettings):
    """ Configurações comuns aos módulos da suíte """
    #Configurações do Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis") #Endereço do servidor Redis
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379")) #Porta de conexão
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0")) #Número do banco utilizado
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "") #Senha do Redis, se houver

    #Limiares e tempos de suspensão do Circuit Breaker
    CIRCUIT_LVL1_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL1_THRESHOLD", "3")) #Falhas p/ nível 1
    CIRCUIT_LVL1_SUSPEND: int = int(os.getenv("CIRCUIT_LVL1_SUSPEND", "300")) #Suspensão em segundos
    CIRCUIT_LVL2_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL2_THRESHOLD", "10")) #Falhas p/ nível 2
    CIRCUIT_LVL2_SUSPEND: int = int(os.getenv("CIRCUIT_LVL2_SUSPEND", "1800")) #Suspensão nível 2
    CIRCUIT_LVL3_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL3_THRESHOLD", "25")) #Falhas p/ nível 3
    CIRCUIT_LVL3_SUSPEND: int = int(os.getenv("CIRCUIT_LVL3_SUSPEND", "7200")) #Suspensão nível 3

    #TTLs Redis centralizados por categoria de uso
    REDIS_TTL_RATE_LIMITING_SECONDS: int = int(os.getenv("REDIS_TTL_RATE_LIMITING_SECONDS", "3600")) #Janelas de rate limit
    REDIS_TTL_LOCKS_SECONDS: int = int(os.getenv("REDIS_TTL_LOCKS_SECONDS", "20")) #Locks distribuídos
    REDIS_TTL_CACHE_DATA_SECONDS: int = int(os.getenv("REDIS_TTL_CACHE_DATA_SECONDS", "300")) #Cache de dados (preço, comparação)
    REDIS_TTL_ROBOTS_CACHE_SECONDS: int = int(os.getenv("REDIS_TTL_ROBOTS_CACHE_SECONDS", "3600")) #Cache de robots.txt
    REDIS_TTL_IDEMPOTENCY_SECONDS: int = int(os.getenv("REDIS_TTL_IDEMPOTENCY_SECONDS", "300")) #Chaves de idempotência

    #Proteção contra tentativas de brute-force
    BRUTE_FORCE_MAX_ATTEMPTS: int = int(os.getenv("BRUTE_FORCE_MAX_ATTEMPTS", "5")) #Tentativas permitidas
    BRUTE_FORCE_BLOCK_DURATION: int = int(os.getenv("BRUTE_FORCE_BLOCK_DURATION", "900")) #Bloqueio em segundos

    #Rate limits para tasks Celery
    SCRAPER_RATE_LIMIT: str = os.getenv("SCRAPER_RATE_LIMIT", "10/m") #Limite de scraping
    COMPETITOR_RATE_LIMIT: str = os.getenv("COMPETITOR_RATE_LIMIT", "10/m") #Limite de concorrentes
    COMPARE_RATE_LIMIT: str = os.getenv("COMPARE_RATE_LIMIT", "120/m") #Limite de comparações
    
    #Parâmetros para comparação de preços
    PRICE_TOLERANCE: float = float(os.getenv("PRICE_TOLERANCE", "0.01")) #Variação permitida
    PRICE_CHANGE_THRESHOLD: float = float(os.getenv("PRICE_CHANGE_THRESHOLD", "0.01")) #Sensibilidade a mudanças

    #TTL do registro de última comparação bem-sucedida
    COMPARISON_LAST_SUCCESS_TTL: int = int(
        os.getenv("COMPARISON_LAST_SUCCESS_TTL", str(86400))
    ) #Expiração do registro

    # Isolamento de DBs Redis por camada (Decisão 5)
    # db 0 → broker Celery | db 1 → result backend | db 2 → operacional (locks, rate limit, cache)
    REDIS_BROKER_DB: int = int(os.getenv("REDIS_BROKER_DB", "0"))
    REDIS_RESULT_DB: int = int(os.getenv("REDIS_RESULT_DB", "1"))
    REDIS_OPERATIONAL_DB: int = int(os.getenv("REDIS_OPERATIONAL_DB", "2"))

    #URLs do Celery (broker e result backend) — podem ser sobrescritas via .env
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "") or ""
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "") or ""

    #DLQ via Redis Streams
    CELERY_DLQ_STREAM_NAME: str = os.getenv("CELERY_DLQ_STREAM_NAME", "celery:dlq")
    CELERY_DLQ_RETENTION_MAX_ENTRIES: int = int(os.getenv("CELERY_DLQ_RETENTION_MAX_ENTRIES", "10000"))

    #TTL dos resultados de tasks no Redis backend — deve ser > COLLECTION_TASK_TIMEOUT
    CELERY_RESULT_EXPIRES: int = int(os.getenv("CELERY_RESULT_EXPIRES", "3600"))

    #Configuração de logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO") #Nível de log do root logger
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json") #Formato de saída (json ou text)

    #Cadência de coleta por nível de estabilidade — compartilhado com market_orchestrator
    COLLECT_INTERVAL_UNSTABLE_MIN: int = int(os.getenv("COLLECT_INTERVAL_UNSTABLE_MIN", str(5 * 60))) #Intervalo mínimo para produtos instáveis
    COLLECT_INTERVAL_UNSTABLE_MAX: int = int(os.getenv("COLLECT_INTERVAL_UNSTABLE_MAX", str(10 * 60))) #Intervalo máximo para produtos instáveis
    COLLECT_INTERVAL_STABLE_MIN: int = int(os.getenv("COLLECT_INTERVAL_STABLE_MIN", str(10 * 60))) #Intervalo mínimo para produtos estáveis
    COLLECT_INTERVAL_STABLE_MAX: int = int(os.getenv("COLLECT_INTERVAL_STABLE_MAX", str(20 * 60))) #Intervalo máximo para produtos estáveis
    COLLECT_INTERVAL_VERY_STABLE_MIN: int = int(os.getenv("COLLECT_INTERVAL_VERY_STABLE_MIN", str(20 * 60))) #Intervalo mínimo para produtos muito estáveis
    COLLECT_INTERVAL_VERY_STABLE_MAX: int = int(os.getenv("COLLECT_INTERVAL_VERY_STABLE_MAX", str(30 * 60))) #Intervalo máximo para produtos muito estáveis
    STABILITY_DAYS_UNSTABLE: int = int(os.getenv("STABILITY_DAYS_UNSTABLE", "1")) #Janela para considerar produto instável
    STABILITY_DAYS_STABLE: int = int(os.getenv("STABILITY_DAYS_STABLE", "3")) #Janela para considerar produto estável
    STABILITY_DAYS_VERY_STABLE: int = int(os.getenv("STABILITY_DAYS_VERY_STABLE", "7")) #Janela para considerar produto muito estável
    SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS: int = int(os.getenv("SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS", str(10 * 60))) #Cooldown adicional após falhas de rate limit

    #Configurações extras do Pydantic
    model_config = ConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def redis_url(self) -> str:
        """ URL genérica (usa REDIS_DB). Preferir redis_operational_url para código de aplicação. """
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def redis_operational_url(self) -> str:
        """ URL do db operacional (locks, rate limiting, cache, DLQ, filas operacionais). """
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_OPERATIONAL_DB}"

    @property
    def celery_broker_url(self) -> str:
        """ URL do broker Celery — env CELERY_BROKER_URL tem precedência. """
        if self.CELERY_BROKER_URL:
            return self.CELERY_BROKER_URL
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_BROKER_DB}"

    @property
    def celery_result_backend_url(self) -> str:
        """ URL do result backend Celery — env CELERY_RESULT_BACKEND tem precedência. """
        if self.CELERY_RESULT_BACKEND:
            return self.CELERY_RESULT_BACKEND
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_RESULT_DB}"
