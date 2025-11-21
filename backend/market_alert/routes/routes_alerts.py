""" Rotas para gerenciamento de regras de alertas """

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from shared.infra.db import get_db
from market_alert.models import User
from market_alert.schemas.schemas_alert_rules import QuickAlertRuleCreate, AlertRuleUpdate, AlertRuleResponse
from market_alert.services.services_alert_rules import (
    create_quick_alert_rule,
    delete_user_alert_rule,
    get_user_alert_rule,
    list_user_alert_rules,
    toggle_user_alert_rule,
    update_user_alert_rule,
)
from market_alert.core.security import get_current_user


router = APIRouter(prefix="/alerts", tags=["Alertas"])
logger = structlog.get_logger("http_route")

@router.post("/", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(request: Request, payload: QuickAlertRuleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Cria uma regra de alerta simplificada para o usuário autenticado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id))
    rule = create_quick_alert_rule(db, user.id, payload)
    logger.info("route_completed", path=request.url.path, method=request.method, status="created", rule_id=str(rule.id))
    return rule

@router.get("/", response_model=List[AlertRuleResponse])
def list_rules(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Lista todas as regras de alerta do usuário """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id))
    rules = list_user_alert_rules(db, user)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(rules))
    return rules

@router.get("/{rule_id}", response_model=AlertRuleResponse)
def get_rule(request: Request, rule_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Obtém uma regra de alerta específica """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), rule_id=str(rule_id))
    rule = get_user_alert_rule(db, user, rule_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", rule_id=str(rule.id))
    return rule

@router.patch("/{rule_id}", response_model=AlertRuleResponse)
def toggle_rule_endpoint(request: Request, rule_id: UUID, enabled: bool, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Ativa ou desativa uma regra de alerta """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), rule_id=str(rule_id), enabled=enabled)
    updated = toggle_user_alert_rule(db, user, rule_id, enabled)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", rule_id=str(rule_id))
    return updated

@router.put("/{rule_id}", response_model=AlertRuleResponse)
def update_rule_endpoint(request: Request, rule_id: UUID, updates: AlertRuleUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Atualiza uma regra de alerta existente """
    logger.info("route_called", path=request.url.path, method=request.method, rule_id=str(rule_id))
    updated_rule = update_user_alert_rule(db, user, rule_id, updates)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", rule_id=str(rule_id))
    return updated_rule

@router.delete("/{rule_id}", response_model=AlertRuleResponse)
def delete_rule_endpoint(request: Request, rule_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Exclui uma regra de alerta """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), rule_id=str(rule_id))
    deleted = delete_user_alert_rule(db, user, rule_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="deleted", rule_id=str(rule_id))
    return deleted
