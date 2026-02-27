""" Inicialização dos modelos para importação do SQLAlchemy 

A organização por blocos ajuda a identificar rapidamente os modelos de cada
feature sem precisar navegar por todos os arquivos internos.
"""

# Modelos de identidade e autenticação.
from .models_login_attempt import LoginAttempt
from .models_refresh_token import RefreshToken
from .models_users import User
from .models_verification import Verification

# Modelos de produtos e comparações de mercado.
from .models_comparisons import PriceComparison, PriceComparisonSummary
from .models_price_history import PriceHistory
from .models_products import CompetitorProduct, MonitoredProduct

# Modelos de notificações e observabilidade.
from .models_notifications import (
    AlertRule,
    EventLog,
    Notification,
    NotificationAttempt,
    UserNotificationPreference,
)
from .models_scraping_errors import ScrapingError
from .models_task_failures import TaskFailure

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
