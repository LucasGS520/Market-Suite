""" Esquemas de dados utilizados pelo serviço de scraping """

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class ScraperRequest(BaseModel):
    """ Estrutura esperada na requisição de scraping de anúncios """

    url: HttpUrl
    product_type: Literal["monitored", "competitor"] = "monitored"
    user_id: UUID | None = None

class ScraperResponse(BaseModel):
    """ Dados retornados após o processamento do scraping """

    name: str | None = None
    current_price: float
    old_price: float | None = None
    thumbnail: str | None = None
    free_shipping: bool = False
    seller: str | None = None
    shipping: str | None = None
