""" Define parâmetros de configuração compartilhados entre os serviços

Este módulo centraliza variáveis de ambiente usadas tanto pelo
`market_alert` quanto pelo `market_scraper`, servindo como base para as
configurações específicas de cada serviço.
"""

import os
from dotenv import load_dotenv
from pydantic import AnyHttpUrl, ConfigDict
from pydantic_settings import BaseSettings


#Carrega as variáveis do arquivo .env
load_dotenv()

__all__ = ["ConfigBase"]


class ConfigBase(BaseSettings):
    """ Configurações comuns aos módulos da suíte """
    #Configurações do Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    #Chaves usadas pelo Circuit Breaker
    CIRCUIT_FAILURES_KEY: str = os.getenv("CIRCUIT_FAILURES_KEY", "circuit:failures")
    CIRCUIT_SUSPEND_KEY: str = os.getenv("CIRCUIT_SUSPEND_KEY", "circuit:suspend")

    #Limiares e tempos de suspensão do Circuit Breaker
    CIRCUIT_LVL1_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL1_THRESHOLD", "3"))
    CIRCUIT_LVL1_SUSPEND: int = int(os.getenv("CIRCUIT_LVL1_SUSPEND", "300"))
    CIRCUIT_LVL2_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL2_THRESHOLD", "10"))
    CIRCUIT_LVL2_SUSPEND: int = int(os.getenv("CIRCUIT_LVL2_SUSPEND", "1800"))
    CIRCUIT_LVL3_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL3_THRESHOLD", "25"))
    CIRCUIT_LVL3_SUSPEND: int = int(os.getenv("CIRCUIT_LVL3_SUSPEND", "7200"))

    #Webhook Slack para notificações críticas
    SLACK_WEBHOOK_URL: AnyHttpUrl | None = os.getenv("SLACK_WEBHOOK_URL", None)

    #Configurações de cache do robots.txt
    ROBOTS_CACHE_KEY: str = os.getenv("ROBOTS_CACHE_KEY", "robots.txt:content")
    ROBOTS_CACHE_TTL: int = int(os.getenv("ROBOTS_CACHE_TTL", str(24 * 3600)))

    #Proteção contra tentativas de brute-force
    BRUTE_FORCE_MAX_ATTEMPTS: int = int(os.getenv("BRUTE_FORCE_MAX_ATTEMPTS", "5"))
    BRUTE_FORCE_BLOCK_DURATION: int = int(os.getenv("BRUTE_FORCE_BLOCK_DURATION", "900"))

    #Rate limits para tasks Celery
    SCRAPER_RATE_LIMIT: str = os.getenv("SCRAPER_RATE_LIMIT", "10/m")
    COMPETITOR_RATE_LIMIT: str = os.getenv("COMPETITOR_RATE_LIMIT", "10/m")
    COMPARE_RATE_LIMIT: str = os.getenv("COMPARE_RATE_LIMIT", "120/m")
    ALERT_RATE_LIMIT: str = os.getenv("ALERT_RATE_LIMIT", "60/m")
    ALERT_DUPLICATE_WINDOW: int = int(os.getenv("ALERT_DUPLICATE_WINDOW", 600))
    ALERT_RULE_COOLDOWN: int = int(os.getenv("ALERT_RULE_COOLDOWN", "3600"))

    #Parâmetros para comparação de preços
    PRICE_TOLERANCE: float = float(os.getenv("PRICE_TOLERANCE", "0.01"))
    PRICE_CHANGE_THRESHOLD: float = float(os.getenv("PRICE_CHANGE_THRESHOLD", "0.01"))

    #TTL do registro de última comparação bem-sucedida
    COMPARISON_LAST_SUCCESS_TTL: int = int(
        os.getenv("COMPARISON_LAST_SUCCESS_TTL", str(86400))
    )

    #Configurações extras do Pydantic
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def redis_url(self) -> str:
        """ URL completa para conectar ao Redis """
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
