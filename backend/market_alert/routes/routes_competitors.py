""" Rotas para gerenciamento de produtos concorrentes monitorados """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from shared.infra.db import get_db
from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping

from market_alert.models import User
from market_alert.schemas.schemas_products import CompetitorProductResponse
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_competitor import (
    get_competitors_by_monitored_id,
    delete_competitors_by_monitored_id,
    get_competitor_by_monitored_and_url,
    count_competitors_by_monitored,
)
from market_alert.tasks.scraper_tasks import collect_competitor_task
from market_alert.core.security import get_current_user
from market_alert.core.config_alert import settings

from shared.utils.url_validation import normalize_and_validate_product_url


router = APIRouter(prefix="/competitors", tags=["Concorrentes"])
logger = structlog.get_logger("http_route")

@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def create_competitor_scrape(request: Request, product_data: CompetitorProductCreateScraping, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para monitorar e comparar um produto concorrente por meio de um link direto (scraping) """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(product_data.monitored_product_id))

    try:
        normalized_url, issue = normalize_and_validate_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_competitor_url", url=str(product_data.product_url), error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if issue:
        logger.warning("invalid_competitor_url", url=normalized_url, code=issue.code)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message)

    #Valida se o produto monitorado existe e pertence ao usuário antes de agendar scraping
    mp = get_monitored_product_by_id(db, product_data.monitored_product_id)
    if mp is None:
        logger.warning(
            "route_error",
            path=request.url.path,
            method=request.method,
            reason="not_found",
            monitored_id=str(product_data.monitored_product_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto monitorado não encontrado.",
        )
    
    if mp.user_id != user.id:
        logger.warning(
            "route_error",
            path=request.url.path,
            method=request.method,
            reason="forbidden",
            monitored_id=str(product_data.monitored_product_id),
            owner_id=str(mp.user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário não possui permissão para acessar este produto monitorado.",
        )

    #Checa duplicidade com base na URL canônica
    existing = get_competitor_by_monitored_and_url(db, mp.id, normalized_url)
    if existing:
        logger.info(
            "competitor_existis",
            path=request.url.path,
            method=request.method,
            monitored_id=str(mp.id),
            competitor_id=str(existing.id),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concorrente já cadastrado para este produto monitorado.",
        )
    
    competitors_total = count_competitors_by_monitored(db, mp.id)
    if competitors_total >= settings.MAX_COMPETITORS_PER_MONITORED:
        logger.warning(
            "competitor_limit_reached",
            path=request.url.path,
            method=request.method,
            monitored_id=str(mp.id),
            limit=settings.MAX_COMPETITORS_PER_MONITORED,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Limite de concorrentes atingido para este produto monitorado.",
        )

    #Cria um produto concorrente via Celery
    collect_competitor_task.delay(
        monitored_product_id=str(product_data.monitored_product_id),
        url=normalized_url
    )

    logger.info("route_completed", path=request.url.path, method=request.method, status="scheduled")
    return {"message": "Scraping de concorrente agendado com sucesso."}

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
