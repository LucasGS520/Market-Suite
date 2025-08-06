""" Carrega variáveis de ambiente e configurações da aplicação

Este módulo provê apenas parâmetros relacionados ao processo de
*scraping*. Ele não cuida de persistência de dados e nem
de autenticação, responsabilidades delegadas a outros componentes
do sistema.
"""

import os
from dotenv import load_dotenv
from pydantic import AnyHttpUrl, ConfigDict
from pydantic_settings import BaseSettings


#Carrega as variáveis do .env
load_dotenv()

#Declara símbolos públicos para satisfazer o lint
__all__ = ["Settings", "settings"]

class Settings(BaseSettings):
    """ Classe de configurações centrais da aplicação """

    #Configurações do Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    #Chaves usadas pelo Circuit Breaker
    CIRCUIT_FAILURES_KEY: str = os.getenv("CIRCUIT_FAILURES_KEY", "circuit:failures")
    CIRCUIT_SUSPEND_KEY: str = os.getenv("CIRCUIT_SUSPEND_KEY", "circuit:suspend")

    #Limiares (thresholds) e tempos de suspensão (segundos) do Circuit Breaker
    CIRCUIT_LVL1_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL1_THRESHOLD", "3"))
    CIRCUIT_LVL1_SUSPEND: int = int(os.getenv("CIRCUIT_LVL1_SUSPEND", "300"))
    CIRCUIT_LVL2_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL2_THRESHOLD", "10"))
    CIRCUIT_LVL2_SUSPEND: int = int(os.getenv("CIRCUIT_LVL2_SUSPEND", "1800"))
    CIRCUIT_LVL3_THRESHOLD: int = int(os.getenv("CIRCUIT_LVL3_THRESHOLD", "25"))
    CIRCUIT_LVL3_SUSPEND: int = int(os.getenv("CIRCUIT_LVL3_SUSPEND", "7200"))

    #Webhook Slack para notificação do level 3
    SLACK_WEBHOOK_URL: AnyHttpUrl | None = os.getenv("SLACK_WEBHOOK_URL", None)

    #Chave e TTL para cachear o robots.txt no Redis
    ROBOTS_CACHE_KEY: str = os.getenv("ROBOTS_CACHE_KEY", "robots.txt:content")
    ROBOTS_CACHE_TTL: int = int(os.getenv("ROBOTS_CACHE_TTL", str(24 * 3600)))

    #TTL base do cache de scraping
    CACHE_BASE_TTL: int = int(os.getenv("CACHE_BASE_TTL", str(3600)))

    #Brute-force protection
    BRUTE_FORCE_MAX_ATTEMPTS: int = int(os.getenv("BRUTE_FORCE_MAX_ATTEMPTS", "5"))
    BRUTE_FORCE_BLOCK_DURATION: int = int(os.getenv("BRUTE_FORCE_BLOCK_DURATION", "900"))

    #Parâmetros para o HumanizedDelayManager
    HUMAN_AVG_WPM: int = int(os.getenv("HUMAN_AVG_WPM", "200"))
    HUMAN_BASE_DELAY: float = float(os.getenv("HUMAN_BASE_DELAY", "1.0"))
    HUMAN_FATIGUE_MIN: float = float(os.getenv("HUMAN_FATIGUE_MIN", "0.5"))
    HUMAN_FATIGUE_MAX: float = float(os.getenv("HUMAN_FATIGUE_MAX", "2.0"))

    #Parametros do Throttle e Rate Limiter
    THROTTLE_RATE: float = float(os.getenv("THROTTLE_RATE", "0.2"))
    THROTTLE_CAPACITY: float = float(os.getenv("THROTTLE_CAPACITY", "3"))
    JITTER_MIN: float = float(os.getenv("JITTER_MIN", "2.0"))
    JITTER_MAX: float = float(os.getenv("JITTER_MAX", "7.0"))

    MONITORED_RATE_LIMIT: int = int(os.getenv("MONITORED_RATE_LIMIT", "100"))
    COMPETITOR_SERVICE_RATE_LIMIT: int = int(os.getenv("COMPETITOR_SERVICE_RATE_LIMIT", "200"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "3600"))

    #Rate limits para tasks Celery
    SCRAPER_RATE_LIMIT: str = os.getenv("SCRAPER_RATE_LIMIT", "10/m")
    COMPETITOR_RATE_LIMIT: str = os.getenv("COMPETITOR_RATE_LIMIT", "10/m")
    COMPARE_RATE_LIMIT: str = os.getenv("COMPARE_RATE_LIMIT", "120/m")
    ALERT_RATE_LIMIT: str = os.getenv("ALERT_RATE_LIMIT", "60/m")
    ALERT_DUPLICATE_WINDOW: int = int(os.getenv("ALERT_DUPLICATE_WINDOW", 600))
    ALERT_RULE_COOLDOWN: int = int(os.getenv("ALERT_RULE_COOLDOWN", "3600"))

    #Parametros para comparação de preços
    PRICE_TOLERANCE: float = float(os.getenv("PRICE_TOLERANCE", "0.01"))
    PRICE_CHANGE_THRESHOLD: float = float(os.getenv("PRICE_CHANGE_THRESHOLD", "0.01"))

    #TTL em segundos do registro Redis de última comparação bem-sucedida
    COMPARISON_LAST_SUCCESS_TTL: int = int(os.getenv("COMPARISON_LAST_SUCCESS_TTL", str(86400)))

    #Parametros do Playwright
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "1") == "1"
    PLAYWRIGHT_TIMEOUT: int = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))

    #Intervalo base para o AdaptiveRecheckManager
    ADAPTIVE_RECHECK_BASE_INTERVAL: int = int(os.getenv("ADAPTIVE_RECHECK_BASE_INTERVAL", "7200"))

    #Parâmetros extras de configurações Pydantic
    model_config = ConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        extra = "ignore"
    )

    @property
    def redis_url(self) -> str:
        """ URL completa para conectar no Redis. """
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        #Monta URL seguindo o formato redis://[:pwd@host:port/db]
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

#Instância única de settings para a aplicação
settings = Settings()
