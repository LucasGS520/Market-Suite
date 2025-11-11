""" Modelos Pydantic compartilhados para produtos monitorados e concorrentes """

from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, ConfigDict, field_validator


# ----- PRODUTO MONITORADO -----
class MonitoredProductCreateScraping(BaseModel):
    """ Esquema compartilhado para criação de produto monitorado via scraping sem preço alvo """

    model_config = ConfigDict(extra="ignore")
    name_identification: str | None = Field(
        default=None,
        description="Nome do produto para identificação"
    )
    product_url: HttpUrl = Field(..., description="link do produto que deseja monitorar")

    @field_validator("name_identification", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: str | None) -> str | None:
        """ Converte strings vazias em ``None`` para acionar fallbacks posteriores """
        if isinstance(value, str) and not value.strip():
            return None
        return value

class MonitoredScrapedInfo(BaseModel):
    """ Informações de scraping compartilhadas para produto monitorado """

    current_price: Decimal
    thumbnail: Optional[str] = None
    free_shipping: bool = False
    currency: Optional[str] = None


# ----- PRODUTO CONCORRENTE -----
class CompetitorProductCreateScraping(BaseModel):
    """ Esquema compartilhado para a criação de produto concorrente via scraping """

    monitored_product_id: UUID = Field(..., description="ID do produto monitorado ao qual este concorrente pertence")
    product_url: HttpUrl = Field(..., description="URL do produto concorrente para scraping")

class CompetitorScrapedInfo(BaseModel):
    """ Informações de scraping compartilhadas para produto concorrente """

    name: str
    current_price: Decimal
    old_price: Optional[Decimal] = None
    thumbnail: Optional[str] = None
    free_shipping: bool = False
    seller: Optional[str] = None
    seller_rating: Optional[float] = None
    currency: Optional[str] = None
