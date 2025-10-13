""" Define as rotas responsáveis por acionar o pipeline de scraping """

from __future__ import annotations

from fastapi import APIRouter, Body, status
from fastapi.responses import JSONResponse
import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.schemas.parse import ErrorResponse, ParseRequest, ParserResponse
from market_scraper.services.services_scraper_common import run_pipeline
from market_scraper.services.synergic_pipeline import PipelineTimeoutError
from market_scraper.utils.price import parse_price_str
from market_scraper.utils.url_validation import UrlIssue, check_url_compatibility, normalize_product_url


logger = structlog.get_logger("routes_scraper")

router = APIRouter(tags=["scraper"])

def _http_error(issue: UrlIssue, *, status_code: int) -> JSONResponse:
    """ Cria uma resposta JSON padronizada para os erros do endpoint """
    logger.warning(
        "parse_error", 
        code=issue.code, 
        message=issue.message
    )
    return JSONResponse(
        status_code=status_code,
        content={"message": issue.message, "code": issue.code}
    )

@router.post(
    "/parse",
    response_model=ParserResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def parse_endpoint(payload: ParseRequest = Body(...)) -> ParserResponse:
    """ Executa o pipeline sequencial e retorna payload padronizado """
    try:
        normalized_url = normalize_product_url(payload.url)
    except ValueError as exc:
        return _http_error(
            UrlIssue(code="invalid_url", message=str(exc)), status_code=status.HTTP_400_BAD_REQUEST
        )
    
    compatibility = check_url_compatibility(normalized_url)
    if compatibility:
        return _http_error(
            compatibility,
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        #Mantém a execução encapsulada para registrar métricas e facilitar o controle de timeouts
        outcome = await run_pipeline(normalized_url)
    except PipelineTimeoutError as exc:
        issue = UrlIssue(code="pipeline_timeout", message="Tempo limite do pipeline execedido")
        return _http_error(
            issue,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT
        )
    
    #Identifica se alguma etapa encerrou por causa do robots.txt e devolve o código especializado
    if any(step.message == "unsupported_by_robots" for step in outcome.steps):
        issue = UrlIssue(
            code="unsupported_by_robots",
            message="O acesso à URL foi bloqueado pelas regras do robots.txt",
        )
        return _http_error(
            issue,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if outcome.status != "success" or not outcome.payload:
        issue = UrlIssue(code="no_result", message="Não foi possível extrair dados do produto")
        return _http_error(
            issue,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    
    payload = outcome.payload

    try:
        price = parse_price_str(payload.get("current_price"), normalized_url)
    except ValueError as exc:
        issue = UrlIssue(code="invalid_price", message=str(exc))
        return _http_error(
            issue,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    
    response = ParserResponse(
        name=payload.get("name", ""),
        current_price=price,
        url=payload.get("url", normalized_url),
        source=payload.get("source", outcome.context.source),
    )
    logger.info(
        "parse_success",
        url=sanitize_log_data(response.url),
        source=response.source,
    )
    return response

__all__ = ["router"]
