""" Rotas para consulta de erros de monitoramento """

import structlog
from fastapi import APIRouter, Depends, Query, Request
from uuid import UUID
from sqlalchemy.orm import Session
from typing import List

from infra.db import get_db
from app.core.security import get_current_user
from app.crud.crud_errors import get_recent_scraping_errors, get_scraping_errors_for_product
from app.schemas.schemas_errors import ScrapingErrorResponse


router = APIRouter(prefix="/monitoring_errors", tags=["Monitorar erros de Scraping"])
logger = structlog.get_logger("http_route")

@router.get("/errors", response_model=List[ScrapingErrorResponse])
def list_errors_scraping(request: Request, db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200), product_id: UUID | None = Query(None), user = Depends(get_current_user)):
    """ Retorna os erros de Scraping mais recentes ou de um produto específico """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), limit=limit, product_id=str(product_id) if product_id else None)
    if product_id:
        errors = get_scraping_errors_for_product(db, product_id, limit)
    else:
        errors = get_recent_scraping_errors(db, limit)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(errors))
    return errors
