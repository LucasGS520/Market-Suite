""" Rotas REST de notificações e stub para streaming desativado """

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.core.security import get_current_user
from market_alert.crud.crud_notification_logs import get_notification_logs
from market_alert.enums.enums_alerts import ChannelType
from market_alert.models.models_users import User
from market_alert.schemas.schemas_alert_rules import NotificationLogResponse


router = APIRouter(prefix="/notifications", tags=["Notificações"])
logger = structlog.get_logger("http_route")

@router.get("/ws", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def notifications_stream_disabled() -> JSONResponse:
    """Informa que o canal WebSocket de notificações foi desativado temporariamente."""
    message = {
        "detail": "Streaming de notificações em tempo real está desabilitado temporariamente.",
        "hint": "Consuma notificações pelo endpoint REST /notifications/logs ou via polling.",
    }
    return JSONResponse(status_code=status.HTTP_501_NOT_IMPLEMENTED, content=message)

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
    user: User = Depends(get_current_user),
):
    """ Lista logs de notificações do usuário autenticado preservando paginação e filtros """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        limit=limit,
        offset=offset,
    )

    logs = get_notification_logs(
        db,
        user.id,
        limit=limit,
        offset=offset,
        start=start,
        end=end,
        channel=channel,
        success=success,
        alert_rule_id=alert_rule_id,
        cursor=cursor,
    )
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=len(logs),
    )
    return logs
