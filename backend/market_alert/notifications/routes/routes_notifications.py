""" Rotas para histórico de notificações e preferências do usuário """

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.infraestructure.security.auth_context import get_current_user
from market_alert.models import User
from market_alert.schemas.schemas_notifications import (
    PaginatedNotificationResponse,
    NotificationPaginationMeta,
    UserNotificationPreferenceCreate,
    UserNotificationPreferenceResponse,
)
from market_alert.notifications.crud.crud_notifications import (
    list_notifications_for_user,
    list_user_notification_preferences,
    upsert_user_notification_preference,
)


logger = structlog.get_logger("http_route")
router = APIRouter(prefix="/notifications", tags=["Notificações"])

@router.get("/", response_model=PaginatedNotificationResponse)
def list_notifications(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Página atual (base 1)"),
    per_page: int = Query(25, ge=1, le=200, description="Quantidade de itens por página"),
):
    """ Lista notificações persistidas para o usuário autenticado """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        page=page,
        per_page=per_page,
    )
    items, total = list_notifications_for_user(
        db=db,
        user_id=user.id,
        page=page,
        per_page=per_page,
    )

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=len(items),
        total=total,
    )
    return PaginatedNotificationResponse(
        items=items,
        meta=NotificationPaginationMeta(
            total=total,
            page=page,
            per_page=per_page,
        )
    )

@router.get("/preferences", response_model=list[UserNotificationPreferenceResponse])
def list_preferences(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Retorna preferências de notificação do usuário """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
    )
    preferences=list_user_notification_preferences(db=db, user_id=user.id)
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=len(preferences),
    )
    return preferences

@router.post("/preferences", response_model=UserNotificationPreferenceResponse, status_code=status.HTTP_201_CREATED)
def upsert_preference(
    request: Request,
    payload: UserNotificationPreferenceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Cria ou atualiza a preferência de usuário para um canal específico """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        channel=payload.channel,
        alert_type=payload.alert_type,
    )
    preference = upsert_user_notification_preference(
        db=db,
        user_id=user.id,
        alert_type=payload.alert_type,
        channel=payload.channel,
        monitored_product_id=payload.monitored_product_id,
        destination=payload.destination,
        enabled=payload.enabled,
        cooldown_seconds=payload.cooldown_seconds,
        channel_metadata=payload.channel_metadata,
        commit=True,
    )
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        preference_id=str(preference.id),
    )
    return preference
