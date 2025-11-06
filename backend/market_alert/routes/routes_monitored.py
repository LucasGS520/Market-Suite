""" Rotas para produtos monitorados pelo usuário """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from shared.infra.db import get_db
from shared.schemas.schemas_products import MonitoredProductCreateScraping

from market_alert.models import User
from market_alert.schemas.schemas_products import MonitoredProductResponse
from market_alert.crud.crud_monitored import get_all_monitored_products, get_monitored_product_by_id, delete_monitored_product
from market_alert.tasks.scraper_tasks import collect_product_task
from market_alert.core.security import get_current_user

from shared.utils.url_validation import check_url_compatibility, normalize_product_url


router = APIRouter(prefix="/monitored", tags=["Monitoramento"])
logger = structlog.get_logger("http_route")

@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def create_scrape_product(request: Request, product_data: MonitoredProductCreateScraping, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para monitorar um produto por meio de um link direto (scraping) """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitoring_type="scraping")

    try:
        normalized_url = normalize_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_product_url", url=str(product_data.product_url), error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    issue = check_url_compatibility(normalized_url)
    if issue:
        logger.warning("invalid_product_url", url=normalized_url, code=issue.code)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message)

    #Cria um produto agendado via celery; envia target_price como string para preservar precisão ao atravessar filas
    collect_product_task.delay(
        url=normalized_url,
        user_id=str(user.id),
        name_identification=product_data.name_identification,
        target_price=str(product_data.target_price)
    )

    logger.info("route_completed", path=request.url.path, method=request.method, status="scheduled")
    return {"message": "Scraping agendado com sucesso. O produto será salvo em breve."}

@router.get("/", response_model=List[MonitoredProductResponse])
def list_monitored_products(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para listar produtos monitorados """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id))
    products = get_all_monitored_products(db, user.id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(products))
    return products

@router.get("/{product_id}", response_model=MonitoredProductResponse)
def get_product(request: Request, product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para listar produtos monitorados pelo ID """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), product_id=str(product_id))
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", product_id=str(product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return product

@router.delete("/{product_id}", response_model=MonitoredProductResponse)
def delete_product(request: Request, product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para deletar um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), product_id=str(product_id))
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", product_id=str(product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    deleted = delete_monitored_product(db, product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return deleted
