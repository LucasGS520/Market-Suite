""" Rotas HTTP para parsing de produtos

Permite a serviços enviar uma URL e receber os dados do anúncio sem persistência. 
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID
from urllib.parse import urlparse

from fastapi import APIRouter, Body, HTTPException, Response, status
import structlog

from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from shared.schemas.schemas_scraper import ScraperRequest, ScraperResponse

from market_scraper.services.services_scraper_common import scrape_product_common_async
from market_scraper.utils.price import parse_price_str
from market_scraper.utils.url_validation import check_url_compatibility


#Logger estruturado para acompanhar as requisições do scraper
logger = structlog.get_logger(__name__)

#Roteador sem prefixo; caminhos base definidos na aplicação principal
router = APIRouter(tags=["scraper"])

@router.post("/parse", response_model=ScraperResponse)
async def parse_endpoint(payload: ScraperRequest = Body(..., example={"url": "https://www.mercadolivre.com.br/MLB-1", "product_type": "monitored"})) -> ScraperResponse:
    """ Executa o scraping e retorna apenas os dados parseados

    Valida o corpo e o domínio; responde 304 quando não há
    mudanças ou informa bloqueios do marketplace.
    """
    incompatibility = check_url_compatibility(str(payload.url))
    if incompatibility:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=incompatibility,
        )

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
        #Registra o resultado retornado pelo serviço quando o scraping falha
        message = result.get("detail") or result.get("message") or "Não foi possível extrair dados do produto"
        logger.error("scrape_failed", status=result.get("status"), detail=message, url=str(payload.url))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message,
        )

    parsed = urlparse(str(payload.url))
    #Extrai o hostname; usa ``netloc`` como fallback para identificar marketplace
    marketplace = parsed.hostname or parsed.netloc

    return ScraperResponse(
        name=details.get("name"),
        #Converte strings de preço para ``Decimal`` garantindo precisão
        current_price=parse_price_str(details.get("current_price"), str(payload.url)),
        marketplace=marketplace,
    )
