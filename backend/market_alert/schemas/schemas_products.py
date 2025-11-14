""" Esquemas Pydantic exclusivos do serviço `market_alert`

Os esquemas de scraping agora são compartilhados em ``shared.schemas.products``
"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus


class MonitoredProductResponse(BaseModel):
    """ Dados retornados após o monitoramento de um produto """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name_identification: Optional[str] = None
    monitoring_type: MonitoringType
    search_query: Optional[str] = None
    product_url: Optional[HttpUrl] = None
    current_price: Optional[Decimal] = None
    free_shipping: Optional[bool]
    thumbnail: Optional[HttpUrl]
    status: MonitoredStatus
    last_checked: Optional[datetime] = None
    competitors_count: int | None = None
    competitors_mean: Optional[str] = None
    competitors_min: Optional[str] = None
    competitors_max: Optional[str] = None
    position_rank: Optional[int] = None
    potential_savings: Optional[str] = None
    competitors_with_price_count: Optional[int] = None
    latest_comparison_id: Optional[UUID] = None
    last_comparison_at: Optional[datetime] = None
    summary_computed_at: Optional[datetime] = None
    is_new: Optional[bool] = None
    comparison_insights: Optional[str] = None

class PaginatedMonitoredProductsResponse(BaseModel):
    """ Envelope de paginação utilizado na listagem de produtos monitorados """
    items: list[MonitoredProductResponse]
    total: int
    page: int
    per_page: int

class CompetitorProductResponse(BaseModel):
    """ Informações de produtos concorrentes extraídas do scrapping """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    monitored_product_id: UUID
    name_competitor: str = Field(..., description="Nome do produto concorrente")
    product_url: HttpUrl = Field(..., description="Link do produto")
    current_price: Decimal
    old_price: Optional[Decimal]
    free_shipping: Optional[bool]
    seller: Optional[str]
    seller_rating: Optional[float]
    thumbnail: Optional[HttpUrl]
    status: ProductStatus
    last_checked: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_paused: bool

class CompetitorListItemResponse(BaseModel):
    """ Estrutura resumida usada na listagem paginada de concorrentes """
    id: UUID
    monitored_product_id: UUID
    name: str
    product_url: HttpUrl
    current_price: Optional[str]
    previous_price: Optional[str]
    price_change: Optional[str]
    price_change_percentage: Optional[str]
    status: ProductStatus
    last_checked: Optional[datetime]
    is_paused: bool


class PaginatedCompetitorResponse(BaseModel):
    """ Envelope padronizado para retornar concorrentes paginados """
    items: list[CompetitorListItemResponse]
    total: int
    page: int
    per_page: int


class BulkCompetitorActionRequest(BaseModel):
    """ Entrada de ações em massa sobre concorrentes específicos """
    monitored_product_id: UUID
    competitor_ids: list[UUID] = Field(..., min_length=1)


class BulkCompetitorActionResult(BaseModel):
    """ Resultado das ações em massa executadas para concorrentes """
    processed_ids: list[UUID]
    skipped_ids: list[UUID]
    total_processed: int
