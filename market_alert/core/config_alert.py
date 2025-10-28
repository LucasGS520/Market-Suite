""" Carrega variáveis de ambiente para o serviço de alertas

Este módulo estende as configurações compartilhadas em
`core.config_base`, adicionando apenas parâmetros específicos
do `market_alert`.
"""

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
    SCRAPER_RETRY_ATTEMPTS: int = int(
        os.getenv("SCRAPER_RETRY_ATTEMPTS", "3")
    ) #Número máximo de espera exponencial entre tentativas
    SCRAPER_RETRY_BACKOFF_MIN: float = float(
        os.getenv("SCRAPER_RETRY_BACKOFF_MIN", "0.2")
    ) #Valor mínimo de espera exponencial entre tentativas
    SCRAPER_RETRY_BACKOFF_MAX: float = float(
        os.getenv("SCRAPER_RETRY_BACKOFF_MAX", "2.0")
    ) #Valor máximo de espera exponencial entre tentativas
    SCRAPER_SERVICE_AUTH_HEADER: str | None = os.getenv(
        "SCRAPER_SERVICE_AUTH_HEADER"
    ) #Nome do header opcional para autenticação interna
    SCRAPER_SERVICE_AUTH_TOKEN: str | None = os.getenv(
        "SCRAPER_SERVICE_AUTH_TOKEN"
    ) #Valor enviado no header opcional de autenticação


#Instância única de settings para a aplicação
settings = Settings()
