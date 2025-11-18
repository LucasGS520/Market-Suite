""" Modelos Pydantic compartilhados para produtos monitorados e concorrentes 

Os esquemas deste módulo foram simplificados para expor um contrato único
entre API e scraper, garantindo previsibilidade mínima: identificador,
URL, nome, preço (obrigatório), moeda, timestamp de coleta e fonte
(monitorado ou concorrente). Demais campos são opcionais e servem apenas
como anotações contextuais, evitando sobrecarga de parâmetros pouco
utilizados.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProductCore(BaseModel):
    """ Representação mínima de produto utilizada em scraping e resposta """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    product_id: UUID | None = Field(
        default=None,
        alias="id",
        description="Identificador persistido do produto, quando disponível.",
    )
    product_url: HttpUrl = Field(
        ...,
        alias="url",
        description="URL canônica usada na coleta do produto",
    )
    name: str = Field(
        ..., description="Nome normalizado do produto, usado pelo frontend"
    )
    current_price: Decimal = Field(
        ...,
        alias="price",
        description="Preço atual obrigatório para salvar e exibir o produto",
    )
    currency: Optional[str] = Field(
        None,
        description="Moeda associada ao preço, preferencialmente código ISO.",
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp da coleta, usado para rastrear atualizações.",
    )
    source: Literal["monitored", "competitor"] = Field(
        ..., description="Origem do produto dentro do domínio"
    )
    availability: bool | None = Field(
        None,
        description="Disponibilidade reportada pelo scraper; opcional.",
    )
    last_status: str | None = Field(
        None,
        description="Último status retornado pelo scraper ou API; opcional.",
    )


# ----- PRODUTO MONITORADO -----
class MonitoredProductCreateScraping(BaseModel):
    """ Esquema compartilhado para criação de produto monitorado via scraping """
    
    model_config = ConfigDict(extra="ignore")
    name_identification: str | None = Field(
        default=None,
        description="Nome do produto para identificação"
    )
    product_url: HttpUrl = Field(
        ..., description="link do produto que deseja monitorar"
    )

    @field_validator("name_identification", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: str | None) -> str | None:
        """ Normaliza strings vazias para ``None`` e evita rótulos inúteis """
        if isinstance(value, str) and not value.strip():
            return None
        return value

class MonitoredScrapedInfo(ProductCore):
    """ Informações de scraping unificadas para produto monitorado """
    
    source: Literal["monitored"] = Field(
        "monitored",
        description="Origem fixa para produtos monitorados",
    )
    thumbnail: Optional[str] = Field(
        None, description="Imagem opcional retornada pelo scraper"
    )
    free_shipping: bool = Field(
        False, description="Indica se o anúncio foi coletado com frete grátis"
    )


# ----- PRODUTO CONCORRENTE -----
class CompetitorProductCreateScraping(BaseModel):
    """ Esquema compartilhado para a criação de produto concorrente via scraping """

    monitored_product_id: UUID = Field(
        ..., description="ID do produto monitorado ao qual este concorrente pertence"
    )
    product_url: HttpUrl = Field(
        ..., description="URL do produto concorrente para scraping"
    )

class CompetitorScrapedInfo(ProductCore):
    """Informações de scraping unificadas para produto concorrente."""

    source: Literal["competitor"] = Field(
        "competitor",
        description="Origem fixa para produtos concorrentes",
    )
    old_price: Optional[Decimal] = Field(
        None, description="Preço anterior reportado pelo scraper, quando houver"
    )
    thumbnail: Optional[str] = Field(
        None, description="Imagem opcional retornada pelo scraper"
    )
    free_shipping: bool = Field(
        False, description="Indica se o anúncio foi coletado com frete grátis"
    )
    seller: Optional[str] = Field(
        None, description="Nome do vendedor, quando fornecido pela fonte"
    )
    seller_rating: Optional[float] = Field(
        None, description="Avaliação do vendedor retornada pelo marketplace"
    )
