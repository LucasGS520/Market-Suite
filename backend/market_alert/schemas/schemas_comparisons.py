""" Esquema Pydantic utilizados pela API de comparações de Preços """

from uuid import UUID
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


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
    monitored_product_id: UUID
    comparison_id: Optional[UUID] = None
    last_comparison_at: Optional[datetime] = None
    monitored_price: Optional[str] = None
    competitors_count: int = 0
    competitors_with_price_count: int = 0
    competitors_mean: Optional[str] = None
    competitors_min: Optional[str] = None
    competitors_max: Optional[str] = None
    position_rank: Optional[int] = None
    potential_savings: Optional[str] = None
    comparison_insights: Optional[str] = None
    discrepancies: list[Dict[str, Any]] = Field(default_factory=list)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
