""" Reúne e exporta todos os esquemas Pydantic utilizados pela aplicação """

from .schemas_products import MonitoredProductCreateScraping, MonitoredProductResponse, MonitoredScrapedInfo, CompetitorProductCreateScraping, CompetitorProductResponse, CompetitorScrapedInfo
from .schemas_users import UserCreate, UserLogin, UserUpdate, UserResponse
from .schemas_errors import ScrapingErrorResponse
from .schemas_auth import TokenResponse, TokenPairResponse, RefreshRequest, EmailTokenRequest, ResetPasswordRequest, ResetPasswordConfirmRequest, ChangePasswordRequest, ChangeEmailRequest
from .schemas_comparisons import PriceComparisonCreate, PriceComparisonResponse
from .schemas_alert_rules import AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse, NotificationLogResponse, QuickAlertRuleCreate


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredProductResponse",
    "MonitoredScrapedInfo",
    "CompetitorProductCreateScraping",
    "CompetitorProductResponse",
    "CompetitorScrapedInfo",
    "UserCreate",
    "UserLogin",
    "UserUpdate",
    "UserResponse",
    "ScrapingErrorResponse",
    "TokenResponse",
    "TokenPairResponse",
    "RefreshRequest",
    "EmailTokenRequest",
    "ResetPasswordRequest",
    "ResetPasswordConfirmRequest",
    "ChangePasswordRequest",
    "ChangeEmailRequest",
    "PriceComparisonCreate",
    "PriceComparisonResponse",
    "AlertRuleCreate",
    "QuickAlertRuleCreate",
    "AlertRuleUpdate",
    "AlertRuleResponse",
    "NotificationLogResponse"
]
