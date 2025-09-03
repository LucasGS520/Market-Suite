""" Modelos Pydantic compartilhados para requisições e respostas de scraping """

from __future__ import annotations

from typing import Literal
from uuid import UUID
from decimal import Decimal

from pydantic import AnyHttpUrl, BaseModel, field_validator


class ScraperRequest(BaseModel):
    """ Estrutura esperada na requisição de scraping de anúncios

    Este esquema aceita URLs com ou sem esquema definido e garante
    que, na ausência do protocolo, ``https://`` seja automaticamente
    prefixado. Isso facilita o consumo do endpoint por clientes que
    fornecem apenas o domínio ou caminho do recurso.
    """

    url: AnyHttpUrl
    product_type: Literal["monitored", "competitor"] = "monitored"
    user_id: UUID | None = None

    @field_validator("url", mode="before")
    @classmethod
    def ensure_scheme(cls, value: str) -> str:
        """ Garante que a URL possua esquema

        Caso o valor informado não contenha ``http://`` ou ``https://``,
        o protocolo ``https://`` é automaticamente adicionado antes da
        validação do campo.
        """
        if isinstance(value, str) and not value.startswith(("http://", "https://")):
            return f"https://{value}"
        return value

class ScraperResponse(BaseModel):
    """ Dados retornados após o processamento do scraping

    Os campos de preço utilizam ``Decimal`` para preservar a precisão
    durante operações aritméticas e comparações.
    O campo ``marketplace`` registra a origem do anúncio para auditoria.
    """

    name: str | None = None
    current_price: Decimal
    old_price: Decimal | None = None
    thumbnail: str | None = None
    free_shipping: bool = False
    seller: str | None = None
    shipping: str | None = None
    marketplace: str | None = None
