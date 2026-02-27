""" Reúne e exporta todos os esquemas Pydantic utilizados pela aplicação

A exportação foi agrupada por feature para deixar o contrato do pacote mais
legível e simplificar imports de quem consome a API.
"""

from backend.shared.schemas.shared_schemas_products import (
    CompetitorProductCreateScraping,
    CompetitorScrapedInfo,
    InitialCompetitorCreateScraping,
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
)

#Schemas de produtos e scraping.
from .schemas_collection_payload import CollectionPayload
from .schemas_products import (
    CompetitorProductResponse,
    CompetitorScrapeCreationResponse,
    CompetitorsListResponse,
    MonitoredPausedUpdateRequest,
    MonitoredProductResponse,
    MonitoredScrapeCreationResponse,
    PaginatedCompetitorResponse,
    PaginatedMonitoredProductsResponse,
    PaginationMeta,
    ProductResponse,
)

# Schemas de usuários e autenticação.
from .schemas_auth import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    EmailTokenRequest,
    PhoneOtpRequest,
    RefreshRequest,
    ResetPasswordConfirmRequest,
    ResetPasswordRequest,
    TokenPairResponse,
    TokenResponse,
)
from .schemas_users import (
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
    VerificationResendRequest,
)

# Schemas de comparações, configurações e notificações.
from .schemas_comparisons import (
    PaginatedPriceComparisonResponse,
    PriceComparisonCreate,
    PriceComparisonResponse,
    PriceComparisonSummaryResponse,
)
from .schemas_notifications import (
    AlertRuleCreate,
    AlertRuleResponse,
    EventLogCreate,
    EventLogResponse,
    NotificationAttemptCreate,
    NotificationAttemptRead,
    NotificationCreate,
    NotificationPaginationMeta,
    NotificationRead,
    PaginatedNotificationResponse,
    UserNotificationPreferenceCreate,
    UserNotificationPreferenceResponse,
    UserNotificationPreferenceUpdate,
)
from .schemas_settings import (
    NotificationSettings,
    SettingsOverviewResponse,
    SettingsProfileResponse,
    SettingsProfileUpdate,
    SettingsProfileUpdateResponse,
)


# Lista explícita para manter uma superfície pública coesa e previsível.
__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredScrapedInfo",
    "InitialCompetitorCreateScraping",
    "CompetitorProductCreateScraping",
    "CompetitorScrapedInfo",
    "CollectionPayload",
    "ProductResponse",
    "MonitoredScrapeCreationResponse",
    "CompetitorScrapeCreationResponse",
    "MonitoredProductResponse",
    "MonitoredPausedUpdateRequest",
    "PaginatedMonitoredProductsResponse",
    "PaginationMeta",
    "CompetitorProductResponse",
    "PaginatedCompetitorResponse",
    "CompetitorsListResponse",
    "UserCreate",
    "UserLogin",
    "UserUpdate",
    "UserResponse",
    "VerificationResendRequest",
    "TokenResponse",
    "TokenPairResponse",
    "RefreshRequest",
    "EmailTokenRequest",
    "PhoneOtpRequest",
    "ResetPasswordRequest",
    "ResetPasswordConfirmRequest",
    "ChangePasswordRequest",
    "ChangeEmailRequest",
    "PriceComparisonCreate",
    "PriceComparisonResponse",
    "PriceComparisonSummaryResponse",
    "PaginatedPriceComparisonResponse",
    "SettingsOverviewResponse",
    "SettingsProfileResponse",
    "SettingsProfileUpdate",
    "SettingsProfileUpdateResponse",
    "NotificationSettings",
    "EventLogCreate",
    "EventLogResponse",
    "AlertRuleCreate",
    "AlertRuleResponse",
    "NotificationCreate",
    "NotificationRead",
    "NotificationAttemptCreate",
    "NotificationAttemptRead",
    "UserNotificationPreferenceCreate",
    "UserNotificationPreferenceUpdate",
    "UserNotificationPreferenceResponse",
    "NotificationPaginationMeta",
    "PaginatedNotificationResponse",
]
