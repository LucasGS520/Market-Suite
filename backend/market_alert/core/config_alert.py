""" Carrega variáveis de ambiente específicas do serviço `market_alert` """

import os
from pydantic import Field

from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Configurações específicas do serviço de alertas """

    #Configuração do banco de dados
    DATABASE_URL: str = os.getenv("DATABASE_URL")  # URL de conexão do Postgres
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não foi encontrada no arquivo .env.market_alert")

    #Configurações de email SMTP
    SMTP_HOST: str | None = os.getenv("SMTP_HOST") #Endereço do servidor SMTP
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587")) #Porta do SMTP
    SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME") #Usuário para autenticação
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD") #Senha do SMTP
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "1") == "1" #Ativa TLS se igual a "1"
    SMTP_FROM: str | None = os.getenv("SMTP_FROM") #Remetente padrão dos emails

    #Credenciais do Twilio
    TWILIO_ACCOUNT_SID: str | None = os.getenv("TWILIO_ACCOUNT_SID") #SID da conta
    TWILIO_AUTH_TOKEN: str | None = os.getenv("TWILIO_AUTH_TOKEN") #Token de autenticação
    TWILIO_SMS_FROM: str | None = os.getenv("TWILIO_SMS_FROM") #Número de origem SMS
    TWILIO_WHATSAPP_FROM: str | None = os.getenv("TWILIO_WHATSAPP_FROM") #Número de origem WhatsApp

    #Chave do Firebase Cloud Messaging (FCM)
    FCM_SERVER_KEY: str | None = os.getenv("FCM_SERVER_KEY") #Autorização do FCM

    #Segurança e tokens
    SECRET_KEY: str = os.getenv("SECRET_KEY") #Chave para asisnar JWTs
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256") #Algoritmo de assinatura
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7)) #Validade do refresh Token

    #Intervalo base utilizado pelo AdaptiveRecheckManager
    ADAPTIVE_RECHECK_BASE_INTERVAL: int = int(
        os.getenv("ADAPTIVE_RECHECK_BASE_INTERVAL", "7200")
    ) #Base de reagendamento

    #URL base do serviço externo de scraping
    SCRAPER_SERVICE_URL: str = os.getenv(
        "SCRAPER_SERVICE_URL", "http://market_scraper:8000"
    ) #Endpoint do market_scraper
    SCRAPER_CONNECT_TIMEOUT: float = float(
        os.getenv("SCRAPER_CONNECT_TIMEOUT", "5.0")
    ) #Tempo limite de conexão em segundos
    SCRAPER_READ_TIMEOUT: float = float(
        os.getenv("SCRAPER_READ_TIMEOUT", "25.0")
    ) #Tempo limite de leitura em segundos
    SCRAPER_TOTAL_TIMEOUT: float = float(
        os.getenv("SCRAPER_TOTAL_TIMEOUT", "8.0")
    ) #Tempo total máximo da chamada
    SCRAPER_RETRY_ATTEMPTS: int = int(
        os.getenv("SCRAPER_RETRY_ATTEMPTS", "3")
    ) #Número máximo de espera exponencial entre tentativas
    SCRAPER_RETRY_BACKOFF_MIN: float = float(
        os.getenv("SCRAPER_RETRY_BACKOFF_MIN", "0.2")
    ) #Valor mínimo de espera exponencial entre tentativas
    SCRAPER_RETRY_BACKOFF_MAX: float = float(
        os.getenv("SCRAPER_RETRY_BACKOFF_MAX", "2.0")
    ) #Valor máximo de espera exponencial entre tentativas
    SCRAPER_HTTP_MAX_CONNECTIONS: int = int(
        os.getenv("SCRAPER_HTTP_MAX_CONNECTIONS", "100")
    ) #Limite global de conexões HTTP simultâneas
    SCRAPER_HTTP_MAX_KEEPALIVE: int = int(
        os.getenv("SCRAPER_HTTP_MAX_KEEPALIVE", "20")
    ) #Quantidade de conexões mantidas em keep-alive
    SCRAPER_HTTP_KEEPALIVE_EXPIRY: float = float(
        os.getenv("SCRAPER_HTTP_KEEPALIVE_EXPIRY", "30.0")
    ) #Tempo em segundos para expirar conexões inativas
    SCRAPER_SERVICE_AUTH_HEADER: str | None = os.getenv(
        "SCRAPER_SERVICE_AUTH_HEADER"
    ) #Nome do header opcional para autenticação interna
    SCRAPER_SERVICE_AUTH_TOKEN: str | None = os.getenv(
        "SCRAPER_SERVICE_AUTH_TOKEN"
    ) #Valor enviado no header opcional de autenticação
    SCRAPER_HOST_RATE_LIMIT: int = int(
        os.getenv("SCRAPER_HOST_RATE_LIMIT", "20")
    ) #Chamadas máximas por host na janela
    SCRAPER_HOST_RATE_WINDOW_SECONDS: int = int(
        os.getenv("SCRAPER_HOST_RATE_WINDOW_SECONDS", "60")
    ) #Janela de rate limit por host
    SCRAPER_CIRCUIT_FAILURE_THRESHOLD: int = int(
        os.getenv("SCRAPER_CIRCUIT_FAILURE_THRESHOLD", "5")
    ) #Falhas para acionar o circuito
    SCRAPER_CIRCUIT_WINDOW_SECONDS: int = int(
        os.getenv("SCRAPER_CIRCUIT_WINDOW_SECONDS", str(10 * 60))
    ) #Janela de observação de falhas
    SCRAPER_CIRCUIT_COOLDOWN_SECONDS: int = int(
        os.getenv("SCRAPER_CIRCUIT_COOLDOWN_SECONDS", str(30 * 60))
    ) #Tempo de pausa ao abrir circuito
    SCRAPER_FORCE_REFRESH_TTL_SECONDS: int = int(
        os.getenv("SCRAPER_FORCE_REFRESH_TTL_SECONDS", str(24 * 60 * 60))
    ) #Intervalo para forçar reprocessamento completo
    SCRAPER_NO_RESULT_RETRY_SECONDS: int = int(
        os.getenv("SCRAPER_NO_RESULT_RETRY_SECONDS", str(15 * 60))
    ) #Espera mínima antes de reprocessar no_result
    SCRAPER_MAX_RETRY_DELAY_SECONDS: int = int(
        os.getenv("SCRAPER_MAX_RETRY_DELAY_SECONDS", str(5 * 60))
    ) #Limite superior para backoff de Celery
    MAX_COMPETITORS_PER_MONITORED: int = int(
        os.getenv("MAX_COMPETITORS_PER_MONITORED", "10")
    ) #Limite padrão de concorrentes por produto monitorado
    IDEMPOTENCY_TTL_SECONDS: int = int(
        os.getenv("IDEMPOTENCY_TTL_SECONDS", str(60 * 60))
    ) #Tempo padrão para reter chaves de idempotência (1h)
    COMPARISON_IDEMPOTENCY_TTL_SECONDS: int = int(
        os.getenv("COMPARISON_IDEMPOTENCY_TTL_SECONDS", str(60 * 60))
    ) #TTL específico para deduplicação de comparações automáticas
    COMPARISON_STORE_RAW_RESULT: bool = os.getenv(
        "COMPARISON_STORE_RAW_RESULT", "0"
    ).lower() in {"1", "true", "yes", "on"} #Habilita persistência do payload completo para depuração

#Instância única de settings para a aplicação
settings = Settings()
