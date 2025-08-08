""" Modelos pydantic mínimos utilizados durante o scraping """

from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, HttpUrl, Field


class MonitoredProductCreateScraping(BaseModel):
    """ Dados necessários para iniciar o monitoramento via scraping """

    name_identification: str = Field(..., description="Nome do produto para identificação")
    product_url: HttpUrl = Field(..., description="Link do produto que deseja monitorar")
    target_price: Decimal = Field(..., description="Preço-alvo definido")

class CompetitorProductCreateScraping(BaseModel):
    """ Informações básicas de um concorrente para scraping """

    monitored_product_id: UUID = Field(..., description="ID do produto monitorado ao qual o concorrente pertence")
    product_url: HttpUrl = Field(..., description="URL do produto concorrente")
