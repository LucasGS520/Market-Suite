""" Esquemas Pydantic exclusivos do serviço `market_alert` """

from typing import Literal, Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProductResponse(BaseModel):
    """Visão simplificada do produto exposta pela API pública."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str = Field(..., description="Nome preparado para exibição")
    product_url: HttpUrl = Field(..., description="Endereço canônico do produto")
    current_price: Decimal = Field(..., description="Preço obrigatório para exibição")
    currency: Optional[str] = Field(None, description="Moeda do preço informado")
    collected_at: datetime = Field(..., description="Momento da última coleta bem-sucedida")
    source: Literal["monitored", "competitor"]
    availability: bool | None = Field(None, description="Disponibilidade reportada pelo fluxo de coleta")
    last_status: str | None = Field(None, description="Status mais recente conhecido do fluxo de coleta")


# ----- PRODUTO MONITORADO -----
class MonitoredProductResponse(ProductResponse):
    """ Contrato simplificado de um produto monitorado """
    source: Literal["monitored"] = "monitored"
    is_featured: bool = Field(False, description="Indica se o item deve ser exibido como destaque")

class PaginatedMonitoredProductsResponse(BaseModel):
    """ Envelope de paginação para produtos monitorados """
    items: list[MonitoredProductResponse]
    total: int
    page: int
    per_page: int

# ----- PRODUTO CONCORRENTE -----
class CompetitorProductResponse(ProductResponse):
    """ Contrato simplificado de um produto concorrente """
    monitored_product_id: UUID = Field(
        ..., description="Vínculo obrigatório com o produto monitorado"
    )
    source: Literal["competitor"] = "competitor"
    is_paused: bool = Field(False, description="Indica se o monitoramento do concorrente está pausado")

class PaginatedCompetitorResponse(BaseModel):
    """Envelope padronizado para retornar concorrentes paginados."""
    items: list[CompetitorProductResponse]
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
