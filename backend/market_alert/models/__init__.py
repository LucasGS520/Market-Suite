""" Inicialização dos modelos para importação do SQLAlchemy 

Este módulo concentra os modelos usados por importações externas para manter
um contrato estável de pacote após refactors internos de organização.
"""

from market_alert.models.models_comparisons import PriceComparison, PriceComparisonSummary
from market_alert.models.models_login_attempt import LoginAttempt
from market_alert.models.models_notifications import (
    AlertRule,
    EventLog,
    Notification,
    NotificationAttempt,
    UserNotificationPreference,
)
from market_alert.models.models_price_history import PriceHistory
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.models.models_refresh_token import RefreshToken
from market_alert.models.models_scraping_errors import ScrapingError
from market_alert.models.models_task_failures import TaskFailure
from market_alert.models.models_users import User
from market_alert.models.models_verification import Verification

__all__ = [
    "AlertRule",
    "CompetitorProduct",
    "EventLog",
    "LoginAttempt",
    "MonitoredProduct",
    "Notification",
    "NotificationAttempt",
    "PriceComparison",
    "PriceComparisonSummary",
    "PriceHistory",
    "RefreshToken",
    "ScrapingError",
    "TaskFailure",
    "User",
    "UserNotificationPreference",
    "Verification",
]
