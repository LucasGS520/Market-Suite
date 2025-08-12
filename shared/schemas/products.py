""" Modelos Pydantic compartilhados para produtos monitorados e concorrentes """

from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


# ----- PRODUTO MONITORADO -----
class MonitoredProductCreateScraping(BaseModel):
    """ Esquema compartilhado para criação de produto monitorado via scraping """

    name_identification: str = Field(..., description="Nome do produto para identificação")
    product_url: HttpUrl = Field(..., description="link do produto que deseja monitorar")
    target_price: Decimal = Field(..., description="Preço-alvo definido")

class MonitoredScrapedInfo(BaseModel):
    """ Informações de scraping compartilhadas para produto monitorado """

    current_price: Decimal
    thumbnail: Optional[str] = None
    free_shipping: bool = False


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
