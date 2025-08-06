""" Rotas HTTP que expõem o parsing de produtos

Permite que serviços externos enviem uma URL e recebam de volta
os dados estruturados do anúncio, sem qualquer persistência de dados.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from app.services.services_scraper_common import _scrape_product_common
from app.schemas.schemas_products import (
    MonitoredProductCreateScraping,
    CompetitorProductCreateScraping,
)
from app.utils.price import parse_price_str, parse_optional_price_str


router = APIRouter(prefix="/scraper", tags=["scraper"])

class ScrapeRequest(BaseModel):
    """ Corpo da requisição de scraping """

    url: HttpUrl
    product_type: Literal["monitored", "competitor"] = "monitored"
    user_id: UUID | None = None

class ScrapeResponse(BaseModel):
    """ Resposta com os dados extraídos do anúncio """

    name: str | None = None
    current_price: float
    old_price: float | None = None
    thumbnail: str | None = None
    free_shipping: bool = False
    seller: str | None = None
    shipping: str | None = None

@router.post("/parse", response_model=ScrapeResponse)
async def parse_endpoint(payload: ScrapeRequest) -> ScrapeResponse:
    """ Executa o scraping e retorna apenas os dados parseados """

    if payload.product_type == "monitored":
        base_payload = MonitoredProductCreateScraping(
            name_identification="temp",
            product_url=payload.url,
            target_price=Decimal("0"),
        )
    else:
        base_payload = CompetitorProductCreateScraping(
            monitored_product_id=UUID(int=0),
            product_url=payload.url,
        )

    result = await _scrape_product_common(
        url=str(payload.url),
        user_id=payload.user_id or UUID(int=0),
        payload=base_payload,
        product_type=payload.product_type,
        persist_fn=None,
    )

    details = result.get("details")
    if not details:
        raise HTTPException(status_code=500, detail="Falha ao extrair dados")

    return ScrapeResponse(
        name=details.get("name"),
        current_price=float(parse_price_str(details.get("current_price"), str(payload.url))),
        old_price=float(parse_optional_price_str(details.get("old_price"), str(payload.url)))
        if details.get("old_price")
        else None,
        thumbnail=details.get("thumbnail"),
        free_shipping=details.get("shipping") == "Frete Grátis",
        seller=details.get("seller"),
        shipping=details.get("shipping"),
    )
