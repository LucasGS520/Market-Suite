""" Carrega variáveis de ambiente específicas do serviço `market_alert` """

import os
from pydantic import Field

from shared.core.config_base import ConfigBase


__all__ = ["Settings", "settings"]

class Settings(ConfigBase):
    """ Configurações específicas do serviço market_alert """

    #Origens permitidas para CORS no frontend
    _frontend_origins_env = os.getenv("FRONTEND_ORIGINS", "")
    FRONTEND_ORIGINS: list[str] = [
        origin.strip()
        for origin in _frontend_origins_env.split(",")
        if origin.strip()
    ] or [
        #Fallback para ambiente local quando nenhuma origem foi declarada
        #URL do servidor Vite em modo desenvolvimento
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # IP da máquina que serve o frontend na rede local (ex.: seu servidor)
        "http://192.168.15.150:5173",
        #URL do servidor Express utilizado no build de produção local
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Frontend servido a partir do IP (possível variação de porta)
        "http://192.168.15.150:3000",
    ]

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
    #Falha rápida evita tokens sem assinatura forte em ambientes mal configurados
    if not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY não foi encontrada no arquivo .env.market_alert; defina uma chave segura para assinar os JWTs"
        )
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256") #Algoritmo de assinatura
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7)) #Validade do refresh Token
    REFRESH_TOKEN_COOKIE_NAME: str = os.getenv(
        "REFRESH_TOKEN_COOKIE_NAME",
        "refresh_token",
    ) #Nome do cookie utilizado para refresh token
    REFRESH_TOKEN_COOKIE_PATH: str = os.getenv(
        "REFRESH_TOKEN_COOKIE_PATH",
        "/",
    ) #Path restrito para envio do cookie de refresh
    REFRESH_TOKEN_COOKIE_SECURE: bool = os.getenv(
        "REFRESH_TOKEN_COOKIE_SECURE",
        "1",
    ).lower() in {"1", "true", "yes", "on"} #Marca Secure habilitada por padrão
    _refresh_cookie_samesite_env = os.getenv("REFRESH_TOKEN_COOKIE_SAMESITE")
    #Mantém SameSite alinhado ao ambiente quando a variável não estiver declarada
    REFRESH_TOKEN_COOKIE_SAMESITE: str = (
        _refresh_cookie_samesite_env.strip().lower()
        if _refresh_cookie_samesite_env
        else "none"
    ) #Política SameSite do cookie de refresh

    #Controles operacionais de coleta
    PRODUCT_LOCK_TTL_SECONDS: int = int(os.getenv("PRODUCT_LOCK_TTL_SECONDS", "20")) #TTL padrão para lock de produto
    PRODUCT_LOCK_TTL_MIN_SAFE_SECONDS: int = int(
        os.getenv("PRODUCT_LOCK_TTL_MIN_SAFE_SECONDS", "15")
    ) #Margem mínima recomendada para evitar expiração prematura do lock

    #Intervalos do agendamento contínuo (em segundos)
    COLLECT_INTERVAL_UNSTABLE_MIN: int = int(
        os.getenv("COLLECT_INTERVAL_UNSTABLE_MIN", str(5 * 60))
    ) #Intervalo mínimo para produtos instáveis
    COLLECT_INTERVAL_UNSTABLE_MAX: int = int(
        os.getenv("COLLECT_INTERVAL_UNSTABLE_MAX", str(10 * 60))
    ) #Intervalo máximo para produtos instáveis
    COLLECT_INTERVAL_STABLE_MIN: int = int(
        os.getenv("COLLECT_INTERVAL_STABLE_MIN", str(10 * 60))
    ) #Intervalo mínimo para produtos estáveis
    COLLECT_INTERVAL_STABLE_MAX: int = int(
        os.getenv("COLLECT_INTERVAL_STABLE_MAX", str(20 * 60))
    ) #Intervalo máximo para produtos estáveis
    COLLECT_INTERVAL_VERY_STABLE_MIN: int = int(
        os.getenv("COLLECT_INTERVAL_VERY_STABLE_MIN", str(20 * 60))
    ) #Intervalo mínimo para produtos muito estáveis
    COLLECT_INTERVAL_VERY_STABLE_MAX: int = int(
        os.getenv("COLLECT_INTERVAL_VERY_STABLE_MAX", str(30 * 60))
    ) #Intervalo máximo para produtos muito estáveis

    #Thresholds de estabilidade em dias
    STABILITY_DAYS_UNSTABLE: int = int(
        os.getenv("STABILITY_DAYS_UNSTABLE", "1")
    ) #Janela para considerar produto instável
    STABILITY_DAYS_STABLE: int = int(
        os.getenv("STABILITY_DAYS_STABLE", "3")
    ) #Janela para considerar produto estável
    STABILITY_DAYS_VERY_STABLE: int = int(
        os.getenv("STABILITY_DAYS_VERY_STABLE", "7")
    ) #Janela para considerar produto muito estável

    #Configuração do worker contínuo
    CONTINUOUS_WORKER_POLL_INTERVAL: float = float(
        os.getenv("CONTINUOUS_WORKER_POLL_INTERVAL", "1.0")
    ) #Intervalo base entre verificações da fila
    CONTINUOUS_WORKER_BATCH_SIZE: int = int(
        os.getenv("CONTINUOUS_WORKER_BATCH_SIZE", "20")
    ) #Quantidade de itens processados por ciclo
    CONTINUOUS_WORKER_IDLE_SLEEP: float = float(
        os.getenv("CONTINUOUS_WORKER_IDLE_SLEEP", "2.0")
    ) #Pausa aplicada quando a fila está vazia
    CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS: int = int(
        os.getenv("CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS", str(15 * 60))
    ) #TTL para recuperar itens travados no conjunto de processamento
    CONTINUOUS_COLLECTOR_LOCK_TTL_SECONDS: int = int(
        os.getenv("CONTINUOUS_COLLECTOR_LOCK_TTL_SECONDS", "45")
    ) #TTL do lock para garantir instância única do coletor contínuo
    COLLECTION_TASK_TIMEOUT: int = int(
        os.getenv("COLLECTION_TASK_TIMEOUT", "60")
    ) #Timeout em segundos para aguardar AsyncResult de coleta no loop contínuo

    CLEANUP_CACHE_SCAN_COUNT: int = int(
        os.getenv("CLEANUP_CACHE_SCAN_COUNT", "200")
    ) #Quantidade de chaves lidas por iteração do SCAN
    CLEANUP_CACHE_UNLINK_BATCH_SIZE: int = int(
        os.getenv("CLEANUP_CACHE_UNLINK_BATCH_SIZE", "200")
    ) #Quantidade de chaves removidas por lote de UNLINK
    CLEANUP_CACHE_MAX_KEYS_PER_RUN: int = int(
        os.getenv("CLEANUP_CACHE_MAX_KEYS_PER_RUN", "50000")
    ) #Limite defensivo de chaves avaliadas por execução
    CLEANUP_CACHE_MAX_DURATION_SECONDS: float = float(
        os.getenv("CLEANUP_CACHE_MAX_DURATION_SECONDS", "25")
    ) #Tempo máximo de execução para evitar monopolizar o worker
    CLEANUP_CACHE_SLEEP_BETWEEN_BATCHES_MS: int = int(
        os.getenv("CLEANUP_CACHE_SLEEP_BETWEEN_BATCHES_MS", "0")
    ) #Pausa opcional entre lotes para reduzir pressão no Redis

    #Chaves Redis do agendamento contínuo
    PRIORITY_QUEUE_KEY: str = os.getenv(
        "PRIORITY_QUEUE_KEY",
        "market_alert:priority_queue",
    ) #Sorted set principal de agendamento
    PRIORITY_QUEUE_PROCESSING_KEY: str = os.getenv(
        "PRIORITY_QUEUE_PROCESSING_KEY",
        "market_alert:priority_queue:processing",
    ) #Sorted set auxiliar para itens em processamento

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
    SCRAPER_HOST_RETRY_MAX_ATTEMPTS: int = int(
        os.getenv("SCRAPER_HOST_RETRY_MAX_ATTEMPTS", "4")
    ) #Tentativas máximas por host em janela curta
    SCRAPER_HOST_RETRY_WINDOW_SECONDS: int = int(
        os.getenv("SCRAPER_HOST_RETRY_WINDOW_SECONDS", "60")
    ) #Janela para contabilizar tentativas por host
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
    SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS: int = int(
        os.getenv("SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS", str(10 * 60))
    ) #Cooldown adicional após falhas de rate limit
    SCRAPER_INVALID_URL_MAX_ATTEMPTS: int = int(
        os.getenv("SCRAPER_INVALID_URL_MAX_ATTEMPTS", "3")
    ) #Tentativas antes de marcar URL como inválida
    SCRAPER_INVALID_URL_TTL_SECONDS: int = int(
        os.getenv("SCRAPER_INVALID_URL_TTL_SECONDS", str(24 * 60 * 60))
    ) #Janela para contagem de falhas de URL
    MAX_COMPETITORS_PER_MONITORED: int = int(
        os.getenv("MAX_COMPETITORS_PER_MONITORED", "10")
    ) #Limite padrão de concorrentes por produto monitorado

    #Limiares de competitividade para classificação de preços (em porcentagem)
    #COMPETITIVENESS_THRESHOLD_NON_COMPETITIVE_PCT: até 1% acima do menor concorrente → atenção
    #COMPETITIVENESS_THRESHOLD_ATTENTION_PCT: até 5% acima → atenção
    #COMPETITIVENESS_THRESHOLD_URGENT_PCT: acima de 5% → urgente
    COMPETITIVENESS_THRESHOLD_NON_COMPETITIVE_PCT: float = float(
        os.getenv("COMPETITIVENESS_THRESHOLD_NON_COMPETITIVE_PCT", "1")
    ) #Limite superior da faixa de atenção baixa (não-competitivo)
    COMPETITIVENESS_THRESHOLD_ATTENTION_PCT: float = float(
        os.getenv("COMPETITIVENESS_THRESHOLD_ATTENTION_PCT", "5")
    ) #Limite superior da faixa de atenção antes de urgente
    COMPETITIVENESS_THRESHOLD_URGENT_PCT: float = float(
        os.getenv("COMPETITIVENESS_THRESHOLD_URGENT_PCT", "20")
    ) #Referência do limiar urgente (acima de attention_pct já é urgente)
    IDEMPOTENCY_TTL_SECONDS: int = int(
        os.getenv("IDEMPOTENCY_TTL_SECONDS", str(60 * 60))
    ) #Tempo padrão para reter chaves de idempotência (1h)
    COMPARISON_IDEMPOTENCY_TTL_SECONDS: int = int(
        os.getenv("COMPARISON_IDEMPOTENCY_TTL_SECONDS", str(60 * 60))
    ) #TTL específico para deduplicação de comparações automáticas
    COMPARISON_STORE_RAW_RESULT: bool = os.getenv(
        "COMPARISON_STORE_RAW_RESULT", "0"
    ).lower() in {"1", "true", "yes", "on"} #Habilita persistência do payload completo para depuração
    ONBOARDING_ENQUEUE_STAGGER_SECONDS: float = float(
        os.getenv("ONBOARDING_ENQUEUE_STAGGER_SECONDS", "0.5")
    ) #Atraso leve para diluir enfileiramento inicial

    #Configurações da camada de notificações
    DEFAULT_COOLDOWN_SECONDS: int = int(
        os.getenv("DEFAULT_COOLDOWN_SECONDS", "1800")
    ) #Cooldown padrão por monitorado e tipo de alerta
    MIN_PRICE_DELTA_PERCENT: float = float(
        os.getenv("MIN_PRICE_DELTA_PERCENT", "1.0")
    ) #Delta mínimo em porcentagem para alertas de preço
    NOTIFICATION_MAX_ATTEMPTS: int = int(
        os.getenv("NOTIFICATION_MAX_ATTEMPTS", "3")
    ) #Quantidade máxima de tentativas de entrega
    NOTIFICATION_BACKOFF_BASE_SECONDS: int = int(
        os.getenv("NOTIFICATION_BACKOFF_BASE_SECONDS", "60")
    ) #Base de espera para backoff exponencial
    NOTIFICATION_BACKOFF_MULTIPLIER: int = int(
        os.getenv("NOTIFICATION_BACKOFF_MULTIPLIER", "2")
    ) #Multiplicador do backoff exponencial
    NOTIFICATION_EMAIL_PROVIDER: str = os.getenv(
        "NOTIFICATION_EMAIL_PROVIDER", "mock"
    ) #Provider de email configurado (smtp/sendgrid/mock)
    NOTIFICATION_SMS_PROVIDER: str = os.getenv(
        "NOTIFICATION_SMS_PROVIDER", "mock"
    ) #Provider de SMS configurado
    NOTIFICATION_EMAIL_SENDER: str = os.getenv(
        "NOTIFICATION_EMAIL_SENDER", "alerts@marketsuite.local"
    ) #Remetente padrão de emails
    NOTIFICATION_WHATSAPP_PROVIDER: str = os.getenv(
        "NOTIFICATION_WHATSAPP_PROVIDER", "mock"
    ) #Provider de WhatsApp configurado
    NOTIFICATION_PUSH_PROVIDER: str = os.getenv(
        "NOTIFICATION_PUSH_PROVIDER", "mock"
    ) #Provider de push configurado

    #Verificação de cadastro
    EMAIL_VERIFICATION_EXPIRE_MINUTES: int = int(
        os.getenv("EMAIL_VERIFICATION_EXPIRE_MINUTES", "60")
    ) #Validade do token de email em minutos
    PHONE_VERIFICATION_EXPIRE_MINUTES: int = int(
        os.getenv("PHONE_VERIFICATION_EXPIRE_MINUTES", "10")
    ) #Validade do OTP do telefone em minutos
    PHONE_VERIFICATION_MAX_ATTEMPTS: int = int(
        os.getenv("PHONE_VERIFICATION_MAX_ATTEMPTS", "5")
    ) #Tentativas permitidas para OTP
    VERIFICATION_RESEND_INTERVAL_SECONDS: int = int(
        os.getenv("VERIFICATION_RESEND_INTERVAL_SECONDS", "60")
    ) #Intervalo mínimo entre reenvios
    VERIFICATION_RESEND_MAX_PER_HOUR: int = int(
        os.getenv("VERIFICATION_RESEND_MAX_PER_HOUR", "5")
    ) #Limite de reenvios por hora
    REGISTRATION_MAX_PER_HOUR: int = int(
        os.getenv("REGISTRATION_MAX_PER_HOUR", "5")
    ) #Limite de cadastros por hora por IP

#Instância única de settings para a aplicação
settings = Settings()
