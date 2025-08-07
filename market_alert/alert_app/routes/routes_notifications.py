""" Rotas relacionadas a logs de notificações  """

import structlog
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from infra.db import get_db
from app.core.security import get_current_user
from app.schemas.schemas_alert_rules import NotificationLogResponse
from app.crud.crud_notification_logs import get_notification_logs
from app.enums.enums_alerts import ChannelType


router = APIRouter(prefix="/notifications", tags=["Notificações"])
logger = structlog.get_logger("http_route")

@router.get("/logs", response_model=List[NotificationLogResponse])
def list_notification_logs(
        request: Request,
        db: Session = Depends(get_db),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        start: Optional[datetime] = Query(None),
        end: Optional[datetime] = Query(None),
        channel: Optional[ChannelType] = Query(None),
        success: Optional[bool] = Query(None),
        alert_rule_id: Optional[UUID] = Query(None),
        cursor: Optional[datetime] = Query(None),
        user=Depends(get_current_user)
):
    """ Lista os "logs" de notificações do usuário autenticado. """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), limit=limit, offset=offset)

    logs = get_notification_logs(db, user.id, limit=limit, offset=offset, start=start, end=end, channel=channel, success=success, alert_rule_id=alert_rule_id, cursor=cursor)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(logs))
    return logs
