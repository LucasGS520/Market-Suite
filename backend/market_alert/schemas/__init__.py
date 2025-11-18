""" Reúne e exporta todos os esquemas Pydantic utilizados pela aplicação

Os esquemas de scraping de produtos são compartilhados em
``shared.schemas.products`` e importados aqui para conveniência
"""

from backend.shared.schemas.shared_schemas_products import (
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
    CompetitorProductCreateScraping,
    CompetitorScrapedInfo,
)
from .schemas_products import (
    MonitoredProductResponse,
    CompetitorProductResponse,
    PaginatedCompetitorResponse,
    PaginatedMonitoredProductsResponse,
)
from .schemas_users import UserCreate, UserLogin, UserUpdate, UserResponse
from .schemas_errors import ScrapingErrorResponse
from .schemas_auth import TokenResponse, TokenPairResponse, RefreshRequest, EmailTokenRequest, ResetPasswordRequest, ResetPasswordConfirmRequest, ChangePasswordRequest, ChangeEmailRequest
from .schemas_comparisons import PriceComparisonCreate, PriceComparisonResponse
from .schemas_alert_rules import AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse, NotificationLogResponse, QuickAlertRuleCreate


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredProductResponse",
    "PaginatedMonitoredProductsResponse",
    "MonitoredScrapedInfo",
    "CompetitorProductCreateScraping",
    "CompetitorProductResponse",
    "PaginatedCompetitorResponse",
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
