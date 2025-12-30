""" Enumerações relacionadas aos fluxos de notificações e alertas """

from enum import Enum


class EventType(str, Enum):
    """ Tipos de eventos de domínio persistidos """
    price_change = "price_change" #Mudança de preço identificada
    availability_change = "availability_change" #Mudança de disponibilidade identificada
    scraping_error = "scraping_error" #Falha crítica durante scraping
    custom = "custom" #Evento personalizado para integrações futuras

class AlertType(str, Enum):
    """ Tipos de alertas avaliados a partir de eventos """
    price_change = "price_change" #Alerta de mudança de preço
    availability_change = "availability_change" #Alerta de mudança de disponibilidade
    scraping_error = "scraping_error" #Alerta de erro de scraping
    custom = "custom" #Alerta personalizado por regras adicionais

class NotificationChannel(str, Enum):
    """ Canais suportados para entrega de notificações """
    email = "email" #Notificações via email
    sms = "sms" #Notificações via SMS
    push = "push" #Notificações via push
    webhook = "webhook" #Notificações via webhook

class NotificationStatus(str, Enum):
    """ Estado atual de uma notificação persistida """
    pending = "pending" #Pronta para ser enfileirada
    processing = "processing" #Em processo de entrega
    sent = "sent" #Entregue com sucesso
    failed = "failed" #Falha na entrega
    skipped = "skipped" #Ignorada por cooldown ou duplicidade

class DeliveryStatus(str, Enum):
    """ Resultado de uma tentativa de entrega """
    success = "success" #Entrega bem-sucedida
    failed = "failed" #Falha registrada
    