""" Define parâmetros de configuração compartilhados entre os serviços

Este módulo centraliza variáveis de ambiente usadas tanto pelo
`market_alert` quanto pelo `market_scraper`, servindo como base para as
configurações específicas de cada serviço.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import AnyHttpUrl, ConfigDict
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

    #Chaves usadas pelo Circuit Breaker
    CIRCUIT_FAILURES_KEY: str = os.getenv("CIRCUIT_FAILURES_KEY", "circuit:failures") #Hash com contagem de falhas
    CIRCUIT_SUSPEND_KEY: str = os.getenv("CIRCUIT_SUSPEND_KEY", "circuit:suspend") #Flag global de suspensão

    #Limiares e tempos de suspensão do Circuit Breaker
    CIRCUIT_LVL1_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL1_THRESHOLD", "3")) #Falhas p/ nível 1
    CIRCUIT_LVL1_SUSPEND: int = int(os.getenv("CIRCUIT_LVL1_SUSPEND", "300")) #Suspensão em segundos
    CIRCUIT_LVL2_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL2_THRESHOLD", "10")) #Falhas p/ nível 2
    CIRCUIT_LVL2_SUSPEND: int = int(os.getenv("CIRCUIT_LVL2_SUSPEND", "1800")) #Suspensão nível 2
    CIRCUIT_LVL3_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL3_THRESHOLD", "25")) #Falhas p/ nível 3
    CIRCUIT_LVL3_SUSPEND: int = int(os.getenv("CIRCUIT_LVL3_SUSPEND", "7200")) #Suspensão nível 3

    #Webhook Slack para notificações críticas
    SLACK_WEBHOOK_URL: AnyHttpUrl | None = os.getenv("SLACK_WEBHOOK_URL", None)

    #Configurações de cache do robots.txt
    ROBOTS_CACHE_KEY: str = os.getenv("ROBOTS_CACHE_KEY", "robots.txt:content") #Chave base para cache
    ROBOTS_CACHE_TTL: int = int(os.getenv("ROBOTS_CACHE_TTL", str(24 * 3600))) #Tempo de vida do cache

    #Proteção contra tentativas de brute-force
    BRUTE_FORCE_MAX_ATTEMPTS: int = int(os.getenv("BRUTE_FORCE_MAX_ATTEMPTS", "5")) #Tentativas permitidas
    BRUTE_FORCE_BLOCK_DURATION: int = int(os.getenv("BRUTE_FORCE_BLOCK_DURATION", "900")) #Bloqueio em segundos

    #Rate limits para tasks Celery
    SCRAPER_RATE_LIMIT: str = os.getenv("SCRAPER_RATE_LIMIT", "10/m") #Limite de scraping
    COMPETITOR_RATE_LIMIT: str = os.getenv("COMPETITOR_RATE_LIMIT", "10/m") #Limite de concorrentes
    COMPARE_RATE_LIMIT: str = os.getenv("COMPARE_RATE_LIMIT", "120/m") #Limite de comparações
    ALERT_RATE_LIMIT: str = os.getenv("ALERT_RATE_LIMIT", "60/m") #Limite de alertas
    ALERT_DUPLICATE_WINDOW: int = int(os.getenv("ALERT_DUPLICATE_WINDOW", 600)) #Janela anti-duplicação
    ALERT_RULE_COOLDOWN: int = int(os.getenv("ALERT_RULE_COOLDOWN", "3600")) #Intervalo para regras
    ALERT_COOLDOWN_SECONDS: int = int(os.getenv("ALERT_COOLDOWN_SECONDS", str(2 * 3600))) #Cooldown global de alertas
    ALERT_DEDUPE_TTL_SECONDS: int = int(os.getenv("ALERT_DEDUPE_TTL_SECONDS", str(2 * 3600))) #TTL para hash de deduplicação

    #Parâmetros para comparação de preços
    PRICE_TOLERANCE: float = float(os.getenv("PRICE_TOLERANCE", "0.01")) #Variação permitida
    PRICE_CHANGE_THRESHOLD: float = float(os.getenv("PRICE_CHANGE_THRESHOLD", "0.01")) #Sensibilidade a mudanças

    #TTL do registro de última comparação bem-sucedida
    COMPARISON_LAST_SUCCESS_TTL: int = int(
        os.getenv("COMPARISON_LAST_SUCCESS_TTL", str(86400))
    ) #Expiração do registro

    #Configurações extras do Pydantic
    model_config = ConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def redis_url(self) -> str:
        """ URL completa para conectar ao Redis """
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
