""" Esquema Pydantic utilizados pela API de comparações de Preços 

Inclui contratos para criação, visualização detalhada, resumo e paginação
do histórico de comparações. Os números são mantidos como ``Decimal``
para preservar presisão financeira, cabendo à camada de serialização
documentar qualquer conversão adicional.
"""

from uuid import UUID
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from market_alert.enums.enums_comparisons import CompetitivenessStatus


class PriceComparisonCreate(BaseModel):
    """ Esquema para criação de comparação de preços """
    monitored_product_id: UUID
    data: dict[str, Any]

class PriceComparisonResponse(BaseModel):
    """ Dados retornados após comparação """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    monitored_product_id: UUID
    timestamp: datetime
    data: Dict[str, Any]

class PriceComparisonSummaryResponse(BaseModel):
    """ Resumo consolidado da última comparação executada para um produto monitorado """
    #Garante que valores monetários sejam seralizados como números JSON, evitando strings no frontend.
    model_config = ConfigDict(json_encoders={Decimal: float})
    monitored_product_id: UUID
    comparison_id: Optional[UUID] = None
    last_comparison_at: Optional[datetime] = None
    computed_at: Optional[datetime] = None
    monitored_price: Optional[Decimal] = Field(
        default=None,
        description="Preço do produto monitorado na última comparação.",
    )
    competitors_count: int = 0
    competitors_with_price_count: int = 0
    competitors_mean: Optional[Decimal] = Field(
        default=None,
        description="Média de preços dos concorrentes.",
    )
    competitors_min: Optional[Decimal] = Field(
        default=None,
        description="Menor preço entre os concorrentes monitorados.",
    )
    competitors_max: Optional[Decimal] = Field(
        default=None,
        description="Maior preço entre os concorrentes monitorados.",
    )
    position_rank: Optional[int] = None
    potential_adjustment: Optional[Decimal] = Field(
        default=None,
        description="Ajuste potencial calculado contra o menor preço disponível.",
    )
    ignored_due_to_inactive: bool = Field(
        default=False,
        description=(
            "Indica que a comparação foi ignorada porque o produto monitorado estava indisponível ou sem preço válido no momento do cálculo."
        ),
    )
    comparison_insights: Optional[str] = None
    competitiveness_status: Optional[CompetitivenessStatus] = Field(
        default=None,
        description=(
            "Status calculado a partir da diferença percentual para o menor preço "
            "disponível: competitivo, atencao ou urgente."
        ),
    )
    discrepancies: List[Dict[str, Any]] = Field(default_factory=list)

class PaginationMeta(BaseModel):
    """ Informações básicas de paginação utilizadas em respostas listadas """

    total: int = Field(..., description="Total de registros encontrados para o filtro")
    page: int = Field(..., ge=1, description="Página atual (base 1)")
    per_page: int = Field(..., ge=1, description="Quantidade de itens por página")


class PaginatedPriceComparisonResponse(BaseModel):
    """ Envelope paginado para histórico de comparações de preço """

    items: List[PriceComparisonResponse] = Field(
        default_factory=list,
        description="Lista ordenada de comparações para o produto monitorado",
    )
    meta: PaginationMeta
