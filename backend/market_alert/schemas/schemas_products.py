""" Esquemas Pydantic exclusivos do serviço `market_alert` """

from typing import Literal, Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from market_alert.enums.enums_comparisons import CompetitivenessStatus


class ProductResponse(BaseModel):
    """Visão simplificada do produto exposta pela API pública."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str = Field(..., description="Nome preparado para exibição")
    url: HttpUrl = Field(..., description="Endereço canônico do produto")
    current_price: Decimal = Field(..., description="Preço obrigatório para exibição")
    currency: Optional[str] = Field(None, description="Moeda do preço informado")
    collected_at: datetime = Field(..., description="Momento da última coleta bem-sucedida")
    source: Literal["monitored", "competitor"]
    availability: bool | None = Field(None, description="Disponibilidade reportada pelo fluxo de coleta")
    last_status: str | None = Field(None, description="Status mais recente conhecido do fluxo de coleta")

# ----- RETORNOS DE CADASTRO -----
class MonitoredScrapeCreationResponse(BaseModel):
    """ Retorno mínimo ao agendar scraping de produto monitorado """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Identificador do produto monitorado")
    url: HttpUrl = Field(..., description="URL normalizada usada no monitoramento")
    created_at: datetime = Field(..., description="Momento de criação do registro")
    message: str = Field(..., description="Resumo amigável do agendamento")

class CompetitorScrapeCreationResponse(BaseModel):
    """Retorno mínimo ao agendar scraping de um concorrente."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Identificador do concorrente pendente")
    url: HttpUrl = Field(..., description="Endereço canônico normalizado")
    created_at: datetime = Field(..., description="Momento de criação do registro")
    message: str = Field(..., description="Resumo amigável do agendamento")

# ----- PRODUTO MONITORADO -----
class MonitoredProductResponse(ProductResponse):
    """ Contrato simplificado de um produto monitorado """
    owner_id: UUID = Field(..., description="Identificador do responsável pelo monitoramento")
    source: Literal["monitored"] = "monitored"
    thumbnail: str | None = Field(None, description="Miniatura mais recente identificada pelo fluxo de scraping")
    last_scraped_at: datetime | None = Field(None, description="Momento da última extração concluída para o produto")
    competitiveness_status: CompetitivenessStatus | None = Field(None,description="Classificação de competitividade calculada a partir das comparações")
    is_featured: bool = Field(False, description="Indica se o item deve ser exibido como destaque")

class PaginationMeta(BaseModel):
    """ Metadados padronizados para paginação de listagens."""
    total: int = Field(..., description="Quantidade total de registros disponíveis")
    page: int = Field(..., description="Página atual baseada em 1")
    per_page: int = Field(..., description="Quantidade de registros por página")

class PaginatedMonitoredProductsResponse(BaseModel):
    """ Envelope de paginação para produtos monitorados """
    items: list[MonitoredProductResponse]
    meta: PaginationMeta

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
