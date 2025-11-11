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
    last_comparison_at: Optional[datetime] = None
    average_competitor_price: Optional[str] = None
    min_competitor_price: Optional[str] = None
    max_competitor_price: Optional[str] = None
    position_rank: Optional[int] = None
    competitors_count: int = 0
    comparison_insights: Optional[str] = None
    monitored_price: Optional[str] = None
    discrepancies: list[Dict[str, Any]] = Field(default_factory=list)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
