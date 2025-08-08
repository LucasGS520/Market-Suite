""" Carrega variáveis de ambiente para o serviço de alertas

Este módulo estende as configurações compartilhadas em
`core.config_base`, adicionando apenas parâmetros específicos
do `market_alert`.
"""

import os
from pydantic import Field

from core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Configurações específicas do serviço de alertas """

    #Configurações de email SMTP
    SMTP_HOST: str | None = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD")
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "1") == "1"
    SMTP_FROM: str | None = os.getenv("SMTP_FROM")

    #Credenciais do Twilio
    TWILIO_ACCOUNT_SID: str | None = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: str | None = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_SMS_FROM: str | None = os.getenv("TWILIO_SMS_FROM")
    TWILIO_WHATSAPP_FROM: str | None = os.getenv("TWILIO_WHATSAPP_FROM")

    #Chave do Firebase Cloud Messaging (FCM)
    FCM_SERVER_KEY: str | None = os.getenv("FCM_SERVER_KEY")

    #Configuração do banco de dados
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não foi encontrada no .env")

    #Segurança e tokens
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

    #Intervalo base utilizado pelo AdaptiveRecheckManager
    ADAPTIVE_RECHECK_BASE_INTERVAL: int = int(
        os.getenv("ADAPTIVE_RECHECK_BASE_INTERVAL", "7200")
    )

    #URL base do serviço externo de scraping
    SCRAPER_SERVICE_URL: str = os.getenv(
        "SCRAPER_SERVICE_URL", "http://market_scraper:8000"
    )

#Instância única de settings para a aplicação
settings = Settings()
