""" Carrega variáveis de ambiente e configurações da aplicação. """

import os
from dotenv import load_dotenv
from pydantic import AnyHttpUrl, ConfigDict, Field
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

    #TTL em segundos do registro Redis de última comparação bem-sucedida
    COMPARISON_LAST_SUCCESS_TTL: int = int(os.getenv("COMPARISON_LAST_SUCCESS_TTL", str(86400)))

    #Configurações de email SMTP
    SMTP_HOST: str | None = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD")
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "1") == "1"
    SMTP_FROM: str | None = os.getenv("SMTP_FROM")

    #Credenciais do Twilio (SMS e WhatsApp)
    TWILIO_ACCOUNT_SID: str | None = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: str | None = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_SMS_FROM: str | None = os.getenv("TWILIO_SMS_FROM")
    TWILIO_WHATSAPP_FROM: str | None = os.getenv("TWILIO_WHATSAPP_FROM")

    #Chave do Firebase Cloud Messaging (FCM)
    FCM_SERVER_KEY: str | None = os.getenv("FCM_SERVER_KEY")

    #Le a URL do banco
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        #Impede inicialização sem URL de banco
        raise ValueError("DATABASE_URL não foi encontrada no .env")

    #Segurança e tokens
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

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
