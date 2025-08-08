""" Esquemas Pydantic relacionados a produtos monitorados e concorrentes """

from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field, ConfigDict
from decimal import Decimal

from alert_app.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus


# ---------- MONITORED PRODUCT ----------
class MonitoredProductCreateScraping(BaseModel):
    """ Esquema para monitoramento manual via scraping - Usado com link do produto """
    name_identification: str = Field(..., description="Nome do produto para identificação")
    product_url: HttpUrl = Field(..., description="link do produto que deseja monitorar")
    target_price: Decimal = Field(..., description="Preço-alvo definido")


class MonitoredScrapedInfo(BaseModel):
    """ Informações extraídas do HTML do produto monitorado """
    current_price: Decimal
    thumbnail: Optional[str] = None
    free_shipping: bool = False


class MonitoredProductResponse(BaseModel):
    """ Dados retornados após o monitoramento de um produto """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name_identification: Optional[str] = None
    monitoring_type: MonitoringType
    search_query: Optional[str] = None
    product_url: Optional[HttpUrl] = None
    target_price: Decimal
    current_price: Decimal
    free_shipping: Optional[bool]
    thumbnail: Optional[HttpUrl]
    status: MonitoredStatus
    last_checked: Optional[datetime] = None


# ---------- COMPETITOR PRODUCT ----------
class CompetitorProductCreateScraping(BaseModel):
    """ Esquema para criação/atualização de produto manual via scraping - Usado com link do produto """
    monitored_product_id: UUID = Field(..., description="ID do produto monitorado ao qual este concorrente pertence")
    product_url: HttpUrl = Field(..., description="URL do produto concorrente para scraping")


class CompetitorScrapedInfo(BaseModel):
    """ Informações extraídas do HTML do concorrente """
    name: str
    current_price: Decimal
    old_price: Optional[Decimal] = None
    thumbnail: Optional[str] = None
    free_shipping: bool = False
    seller: Optional[str] = None
    seller_rating: Optional[float] = None


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
