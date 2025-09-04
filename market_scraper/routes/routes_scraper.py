""" Rotas HTTP que expõem o parsing de produtos

Permite que serviços externos enviem uma URL e recebam de volta
os dados estruturados do anúncio, sem qualquer persistência de dados.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID
from urllib.parse import urlparse
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Response, status
import structlog
from pydantic import ValidationError

from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from shared.schemas.schemas_scraper import ScraperRequest, ScraperResponse

from market_scraper.services.services_scraper_common import scrape_product_common_async
from market_scraper.utils.price import parse_price_str
from market_scraper.utils.url_validation import check_url_compatibility


#Logger estruturado para acompanhar as requisições do scraper
logger = structlog.get_logger(__name__)

#Roteador sem prefixo; os caminhos base são definidos na aplicação principal
router = APIRouter(tags=["scraper"])

@router.post("/parse", response_model=ScraperResponse)
async def parse_endpoint(payload: Dict[str, Any]) -> ScraperResponse:
    """ Executa o scraping e retorna apenas os dados parseados

    Antes de encaminhar a URL para o serviço de scraping, o corpo da
    requisição é validado manualmente para fornecer mensagens de erro
    mais amigáveis quando a URL for inválida ou não suportada. Caso o
    conteúdo do anúncio não tenha sofrido alterações desde a última
    coleta, o endpoint responde com ``HTTP 304`` sem corpo de resposta
    """

    try:
        data = ScraperRequest(**payload)
    except ValidationError:
        #Retorna erro mais compreensível que o padrão do Pydantic
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL inválida ou malformada",
        )

    incompatibility = check_url_compatibility(str(data.url))
    if incompatibility:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=incompatibility,
        )

    if data.product_type == "monitored":
        base_payload = MonitoredProductCreateScraping(
            name_identification="temp",
            product_url=data.url,
            target_price=Decimal("0"),
        )
    else:
        base_payload = CompetitorProductCreateScraping(
            monitored_product_id=UUID(int=0),
            product_url=data.url,
        )

    result = await scrape_product_common_async(
        url=str(data.url),
        user_id=data.user_id or UUID(int=0),
        payload=base_payload,
        product_type=data.product_type,
    )

    #Quando o serviço indica que o conteúdo não foi modificado, responde com 304
    if result.get("status") == "NOT_MODIFIED":
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    details = result.get("details")
    if not details:
        #Registra o resultado retornado pelo serviço quando o scraping falha
        logger.error("scrape_failed", result=result, url=str(data.url))
        message = result.get("message") or result.get("detail") or "Não foi possível extrair dados do produto"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message
        )

    parsed = urlparse(str(data.url))
    #Extrai o hostname, se não existir usa ``netloc`` como fallback para identificar corretamente o marketplace
    marketplace = parsed.hostname or parsed.netloc

    return ScraperResponse(
        name=details.get("name"),
        #Converte strings de preço para ``Decimal`` garantindo precisão
        current_price=parse_price_str(details.get("current_price"), str(data.url)),
        marketplace=marketplace,
    )
