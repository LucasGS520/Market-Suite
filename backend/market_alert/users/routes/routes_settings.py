""" Rotas de preferências e configurações de usuário """

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.core.security import get_current_user
from market_alert.models.models_users import User
from market_alert.schemas.schemas_settings import (
    NotificationSettings,
    SettingsOverviewResponse,
    SettingsProfileResponse,
    SettingsProfileUpdate,
    SettingsProfileUpdateResponse,
)
from market_alert.users.services import (
    get_notification_settings,
    get_profile_settings,
    get_settings_overview,
    update_notification_settings,
    update_profile_settings,
)


router = APIRouter(prefix="/settings", tags=["Configurações"])
logger = structlog.get_logger("users.routes.settings")

@router.get("", response_model=SettingsOverviewResponse)
def get_settings_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ Retorna o resumo das configurações para montar a tela """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(current_user.id))
    response = get_settings_overview(db, current_user)
    logger.info("route_completed", path = request.url.path, method=request.method, status="success", user_id=str(current_user.id))
    return response


@router.get("/profile", response_model=SettingsProfileResponse)
def get_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """ Retorna os dados de perfil do usuário autenticado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(current_user.id))
    response = get_profile_settings(current_user)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(current_user.id))
    return response

@router.patch("/profile", response_model=SettingsProfileUpdateResponse)
def update_profile(
    request: Request,
    payload: SettingsProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ Atualiza o perfil do usuário e aciona verificações necessárias """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(current_user.id))
    response = update_profile_settings(db, current_user, payload, request)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(current_user.id))
    return response

@router.get("/notifications", response_model=NotificationSettings)
def get_notifications(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ Retorna preferências globais de canais de notificação """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(current_user.id))
    response = get_notification_settings(db, user_id=current_user.id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(current_user.id))
    return response

@router.patch("/notifications", response_model=NotificationSettings)
def update_notifications(
    request: Request,
    payload: NotificationSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ Atualiza preferências globais de canais de notificação """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(current_user.id))
    response = update_notification_settings(db, current_user, payload)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(current_user.id))
    return response
