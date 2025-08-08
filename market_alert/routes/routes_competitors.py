""" Rotas para gerenciamento de produtos concorrentes monitorados """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from infra.db import get_db
from alert_app.models import User
from alert_app.schemas.schemas_products import CompetitorProductCreateScraping, CompetitorProductResponse
from alert_app.crud.crud_monitored import get_monitored_product_by_id
from alert_app.crud.crud_competitor import get_competitors_by_monitored_id, delete_competitors_by_monitored_id
from alert_app.tasks.scraper_tasks import collect_competitor_task
from utils.ml_url import canonicalize_ml_url, is_product_url
from alert_app.core.security import get_current_user


router = APIRouter(prefix="/competitors", tags=["Concorrentes"])
logger = structlog.get_logger("http_route")

@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def create_competitor_scrape(request: Request, product_data: CompetitorProductCreateScraping, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para monitorar e comparar um produto concorrente por meio de um link direto (scraping) """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(product_data.monitored_product_id))

    if not is_product_url(str(product_data.product_url)):
        logger.warning("invalid_competitor_url", url=str(product_data.product_url))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL de produto inválida para Mercado Livre")

    canonical = canonicalize_ml_url(str(product_data.product_url))
    if not canonical:
        logger.warning("invalid_competitor_url", url=str(product_data.product_url))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL de produto inválida para Mercado Livre")

    #Cria um produto concorrente via Celery
    collect_competitor_task.delay(
        monitored_product_id=str(product_data.monitored_product_id),
        url=canonical
    )

    logger.info("route_completed", path=request.url.path, method=request.method, status="scheduled")
    return {"msg": "Scraping de concorrente agendado com sucesso."}

@router.get("/{monitored_product_id}", response_model=List[CompetitorProductResponse])
def list_competitors(request: Request, monitored_product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Lista todos os produtos concorrentes de um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_product_id))

    #Valida produto monitorado pertence ao usuário
    mp = get_monitored_product_by_id(db, monitored_product_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    competitors = get_competitors_by_monitored_id(db, monitored_product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(competitors))
    return competitors

@router.delete("/{monitored_product_id}", response_model=List[CompetitorProductResponse])
def delete_competitors(request: Request, monitored_product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Remove todos os produtos concorrentes de um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_product_id))

    #Valida produto monitorado pertence ao usuário
    mp = get_monitored_product_by_id(db, monitored_product_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    deleted = delete_competitors_by_monitored_id(db, monitored_product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(deleted))
    return deleted
