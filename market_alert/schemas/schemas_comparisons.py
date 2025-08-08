""" Esquema Pydantic utilizados pela API de comparações de Preços """

from uuid import UUID
from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel, ConfigDict


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
