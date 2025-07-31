""" Rotas para gerenciamento de regras de alertas """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from infra.db import get_db
from app.models import User
from app.schemas.schemas_alert_rules import AlertRuleCreate, QuickAlertRuleCreate, AlertRuleUpdate, AlertRuleResponse
from app.crud.crud_alert_rules import create_alert_rule, get_alert_rule, get_user_alert_rules, toggle_alert_rule, update_alert_rule, delete_alert_rule
from app.crud.crud_monitored import get_monitored_product_by_id
from app.core.security import get_current_user


router = APIRouter(prefix="/alert_rules", tags=["Regras de Alertas"])
logger = structlog.get_logger("http_route")

@router.post("/", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(request: Request, payload: QuickAlertRuleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Cria uma regra de alerta para o usuário autenticado de forma simplificada """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id))

    if payload.monitored_product_id:
        mp = get_monitored_product_by_id(db, payload.monitored_product_id)
        if not mp or mp.user_id != user.id:
            logger.warning("route_error", path=request.url.path, method=request.method, reason="invalid_product", product_id=str(payload.monitored_product_id))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Produto monitorado inválido")

    rule_in = AlertRuleCreate(
        user_id=user.id,
        monitored_product_id=payload.monitored_product_id,
        rule_type=payload.rule_type,
        threshold_value=payload.threshold_value,
        threshold_percent=payload.threshold_percent,
        target_price=payload.target_price,
        enabled=True
    )
    rule = create_alert_rule(db, rule_in)
    logger.info("route_completed", path=request.url.path, method=request.method, status="created", rule_id=str(rule.id))
    return rule

@router.get("/", response_model=List[AlertRuleResponse])
def list_rules(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Lista todas as regras de alerta do usuário """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id))

    rules = get_user_alert_rules(db, user.id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(rules))
    return rules

@router.get("/{rule_id}", response_model=AlertRuleResponse)
def get_rule(request: Request, rule_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Obtém uma regra de alerta específica """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), rule_id=str(rule_id))

    rule = get_alert_rule(db, rule_id)
    if not rule or rule.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", rule_id=str(rule_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra de alerta não encontrada")

    logger.info("route_completed", path=request.url.path, method=request.method, status="success", rule_id=str(rule.id))
    return rule

@router.patch("/{rule_id}", response_model=AlertRuleResponse)
def toggle_rule_endpoint(request: Request, rule_id: UUID, enabled: bool, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Ativa ou desativa uma regra de alerta """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), rule_id=str(rule_id), enabled=enabled)

    rule = get_alert_rule(db, rule_id)
    if not rule or rule.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", rule_id=str(rule_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra não encontrada")

    updated = toggle_alert_rule(db, rule_id, enabled)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", rule_id=str(rule_id))
    return updated

@router.put("/{rule_id}", response_model=AlertRuleResponse)
def update_rule_endpoint(request: Request, rule_id: UUID, updates: AlertRuleUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Atualiza uma regra de alerta existente """
    logger.info("route_called", path=request.url.path, method=request.method, rule_id=str(rule_id))

    rule = get_alert_rule(db, rule_id)
    if not rule or rule.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", rule_id=str(rule_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra não encontrada")

    if updates.user_id and updates.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="invalid_user", rule_user=str(updates.user_id))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário inválido para a regra")

    if updates.monitored_product_id:
        mp = get_monitored_product_by_id(db, updates.monitored_product_id)
        if not mp or mp.user_id != user.id:
            logger.warning("route_error", path=request.url.path, method=request.method, reason="invalid_product", product_id=str(updates.monitored_product_id))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Produto monitorado inválido")

    updated_rule = update_alert_rule(db, rule_id, updates)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", rule_id=str(rule_id))
    return updated_rule

@router.delete("/{rule_id}", response_model=AlertRuleResponse)
def delete_rule_endpoint(request: Request, rule_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Exclui uma regra de alerta """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), rule_id=str(rule_id))

    rule = get_alert_rule(db, rule_id)
    if not rule or rule.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", rule_id=str(rule_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra não encontrada")

    deleted = delete_alert_rule(db, rule_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="deleted", rule_id=str(rule_id))
    return deleted
