""" Inicialização dos modelos para importação do SQLAlchemy 

Este ponto centraliza os modelos SQLAlchemy mais importantes para consultas,
relacionamentos e tipagem entre features.
"""

from .models_comparisons import PriceComparison, PriceComparisonSummary
from .models_login_attempt import LoginAttempt
from .models_notifications import (
    AlertRule,
    EventLog,
    Notification,
    NotificationAttempt,
    UserNotificationPreference,
)
from .models_price_history import PriceHistory
from .models_products import CompetitorProduct, MonitoredProduct
from .models_refresh_token import RefreshToken
from .models_scraping_errors import ScrapingError
from .models_task_failures import TaskFailure
from .models_users import User
from .models_verification import Verification

__all__ = [
    "User",
    "Verification",
    "RefreshToken",
    "LoginAttempt",
    "MonitoredProduct",
    "CompetitorProduct",
    "PriceHistory",
    "PriceComparison",
    "PriceComparisonSummary",
    "EventLog",
    "AlertRule",
    "Notification",
    "NotificationAttempt",
    "UserNotificationPreference",
    "ScrapingError",
    "TaskFailure",
]
