""" Tipos de alertas gerados pelo sistema """

from enum import Enum


class AlertType(str, Enum):
    """ Enumeração dos tipos de alertas """
    PRICE_TARGET = "price_target" #Preço alvo atingido
    PRICE_CHANGE = "price_change" #Mudança de preço detectado
    LISTING_PAUSED = "listing_paused" #Anúncio pausado
    LISTING_REMOVED = "listing_removed" #Anúncio removido
    SCRAPING_ERROR = "scraping_error" #Falha ao executar scraping
    SCRAPING_BLOCKED = "scraping_blocked" #Scraping bloqueado temporariamente
    SCRAPING_SUSPENDED = "scraping_suspended" #Scraping suspenso após bloqueios
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open" #CircuitBreaker ativado
    CACHE_MISS_RATE_HIGH = "cache_miss_rate_high" #Taxa de falhas no cache alta
    SYSTEM_ERROR = "system_error" #Erro interno do sistema

class ChannelType(str, Enum):
    """ Enumeração dos canais de notificação """
    EMAIL = "email" #Envio de emails
    SMS = "sms" #Envio de SMS
    PUSH = "push" #Notificação push
    WHATSAPP = "whatsapp" #Envio via WhatsApp
    WEBHOOK = "webhook" #Disparo para webhook
    SLACK = "slack" #Mensagem no Slack
