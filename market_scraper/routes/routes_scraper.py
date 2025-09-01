""" Rotas HTTP que expõem o parsing de produtos

Permite que serviços externos enviem uma URL e recebam de volta
os dados estruturados do anúncio, sem qualquer persistência de dados.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Response, status

from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from shared.schemas.schemas_scraper import ScraperRequest, ScraperResponse

from market_scraper.services.services_scraper_common import scrape_product_common_async
from market_scraper.utils.price import parse_price_str


#Roteador sem prefixo; os caminhos base são definidos na aplicação principal
router = APIRouter(tags=["scraper"])

@router.post("/parse", response_model=ScraperResponse)
async def parse_endpoint(payload: ScraperRequest) -> ScraperResponse:
    """ Executa o scraping e retorna apenas os dados parseados

    Caso o conteúdo não tenha sido modificado desde a última
    coleta, retorna HTTP 304 sem corpo de resposta.
    """

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

    #Quando o serviço indica que o conteúdo não foi modificado, responde com 304
    if result.get("status") == "NOT_MODIFIED":
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    details = result.get("details")
    if not details:
        raise HTTPException(status_code=500, detail="Falha ao extrair dados")

    parsed = urlparse(str(payload.url))
    marketplace = parsed.netloc #Extrai domínio para identificar o marketplace

    return ScraperResponse(
        name=details.get("name"),
        #Converte strings de preço para ``Decimal`` garantindo precisão
        current_price=parse_price_str(details.get("current_price"), str(payload.url)),
        marketplace=marketplace,
    )
