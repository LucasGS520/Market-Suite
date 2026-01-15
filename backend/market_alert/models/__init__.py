""" Inicialização dos modelos para importação do SQLAlchemy """

#Importa os modelos aqui para o SQLAlchemy reconhecer na criação de tabelas
from .models_users import User
from .models_verification import Verification
from .models_products import MonitoredProduct, CompetitorProduct
from .models_price_history import PriceHistory
from .models_scraping_errors import ScrapingError
from .models_comparisons import PriceComparison, PriceComparisonSummary
from .models_notifications import EventLog, AlertRule, Notification, NotificationAttempt, UserNotificationPreference
from .models_refresh_token import RefreshToken

__all__ = [
    "User",
    "Verification",
    "RefreshToken",
    "EventLog",
    "AlertRule",
    "Notification",
    "NotificationAttempt",
    "UserNotificationPreference",
]
