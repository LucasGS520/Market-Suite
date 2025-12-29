""" Reúne e exporta todos os esquemas Pydantic utilizados pela aplicação

Os esquemas de scraping de produtos são compartilhados em
``shared.schemas.products`` e importados aqui para conveniência
"""

from backend.shared.schemas.shared_schemas_products import (
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
    InitialCompetitorCreateScraping,
    CompetitorProductCreateScraping,
    CompetitorScrapedInfo,
)
from .schemas_products import (
    MonitoredProductResponse,
    CompetitorProductResponse,
    PaginatedCompetitorResponse,
    PaginatedMonitoredProductsResponse,
    PaginationMeta,
)
from .schemas_users import UserCreate, UserLogin, UserUpdate, UserResponse
from .schemas_auth import TokenResponse, TokenPairResponse, RefreshRequest, EmailTokenRequest, ResetPasswordRequest, ResetPasswordConfirmRequest, ChangePasswordRequest, ChangeEmailRequest
from .schemas_comparisons import PriceComparisonCreate, PriceComparisonResponse


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredProductResponse",
    "PaginatedMonitoredProductsResponse",
    "PaginationMeta",
    "MonitoredScrapedInfo",
    "InitialCompetitorCreateScraping",
    "CompetitorProductCreateScraping",
    "CompetitorProductResponse",
    "PaginatedCompetitorResponse",
    "CompetitorScrapedInfo",
    "UserCreate",
    "UserLogin",
    "UserUpdate",
    "UserResponse",
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
]
