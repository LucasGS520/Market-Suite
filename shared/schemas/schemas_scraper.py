""" Modelos Pydantic compartilhados para requisições e respostas de scraping """

from __future__ import annotations

from typing import Literal
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, HttpUrl


class ScraperRequest(BaseModel):
    """ Estrutura esperada na requisição de scraping de anúncios """

    url: HttpUrl
    product_type: Literal["monitored", "competitor"] = "monitored"
    user_id: UUID | None = None

class ScraperResponse(BaseModel):
    """ Dados retornados após o processamento do scraping

    Os campos de preço utilizam ``Decimal`` para preservar a precisão
    durante operações aritméticas e comparações
    """

    name: str | None = None
    current_price: Decimal
    old_price: Decimal | None = None
    thumbnail: str | None = None
    free_shipping: bool = False
    seller: str | None = None
    shipping: str | None = None
