""" Rotas HTTP que expõem o parsing de produtos

Permite que serviços externos enviem uma URL e recebam de volta
os dados estruturados do anúncio, sem qualquer persistência de dados.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException

from shared.schemas.products import MonitoredProductCreateScraping, CompetitorProductCreateScraping

from market_scraper.schemas.schemas_scraper import ScraperRequest, ScraperResponse
from market_scraper.services.services_scraper_common import scrape_product_common_async
from market_scraper.utils.price import parse_price_str, parse_optional_price_str


#Roteador sem prefixo; os caminhos base são definidos na aplicação principal
router = APIRouter(tags=["scraper"])

@router.post("/parse", response_model=ScraperResponse)
async def parse_endpoint(payload: ScraperRequest) -> ScraperResponse:
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

    result = await scrape_product_common_async(
        url=str(payload.url),
        user_id=payload.user_id or UUID(int=0),
        payload=base_payload,
        product_type=payload.product_type,
    )

    details = result.get("details")
    if not details:
        raise HTTPException(status_code=500, detail="Falha ao extrair dados")

    return ScraperResponse(
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
