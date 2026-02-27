"""Centraliza as enumerações públicas do domínio `market_alert`.

Este módulo evita que consumidores importem arquivos internos diretamente,
concentrando apenas os tipos de enum mais relevantes para uso externo.
"""

from .enums_comparisons import CompetitivenessStatus
from .enums_notifications import (
    AlertType,
    DeliveryStatus,
    EventType,
    NotificationChannel,
    NotificationStatus,
)
from .enums_products import MonitoredStatus, MonitoringType, ProductStatus
from .enums_users import UserStatus, VerificationKind

# Mantém uma API pública explícita para reduzir acoplamento com a estrutura interna.
__all__ = [
    "MonitoringType",
    "MonitoredStatus",
    "ProductStatus",
    "UserStatus",
    "VerificationKind",
    "CompetitivenessStatus",
    "EventType",
    "AlertType",
    "NotificationChannel",
    "NotificationStatus",
    "DeliveryStatus",
]
