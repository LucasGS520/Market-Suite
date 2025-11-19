""" Esquema Pydantic utilizados pela API de comparações de Preços """

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

class PriceComparisonRunRequest(BaseModel):
    """ Payload opcional utilizado para executar comparação com tolerâncias customizadas """
    tolerance: Decimal | None = Field(
        default=None,
        description="Tolerância absoluta aplicada na comparação de preços.",
    )

class PriceComparisonSummaryResponse(BaseModel):
    """ Resumo consolidado da última comparação executada para um produto monitorado """
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
    comparison_insights: Optional[str] = None
    competitiveness_status: Optional[CompetitivenessStatus] = Field(
        default=None,
        description=(
            "Status calculado a partir da diferença percentual para o menor preço "
            "disponível: competitivo, nao competitivo, atencao ou urgente."
        ),
    )
    discrepancies: List[Dict[str, Any]] = Field(default_factory=list)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
