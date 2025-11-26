""" Serviços centralizados para regras de alerta.

Este módulo concentra validações de domínio, chamadas CRUD e logs
necessários para manipular regras de alertas. Dessa forma, as rotas
podem apenas orquestrar o fluxo HTTP e delegar decisões de negócio
para funções reutilizáveis.
"""

from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from market_alert.crud.crud_alert_rules import (
    create_alert_rule,
    delete_alert_rule,
    get_alert_rule,
    get_user_alert_rules,
    toggle_alert_rule,
    update_alert_rule,
)
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.models import User
from market_alert.models.models_alerts import AlertRule
from market_alert.schemas.schemas_alert_rules import (
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
    QuickAlertRuleCreate,
)


logger = structlog.get_logger("alert_rules_service")

def _validate_monitored_product(db: Session, monitored_product_id: UUID | None, user_id: UUID) -> None:
    """ Garante que o produto monitorado pertence ao usuário autenticado """
    if not monitored_product_id:
        return

    monitored_product = get_monitored_product_by_id(db, monitored_product_id)
    if not monitored_product or monitored_product.user_id != user_id:
        logger.warning(
            "invalid_monitored_product",
            monitored_product_id=str(monitored_product_id),
            user_id=str(user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Produto monitorado inválido",
        )

def _ensure_rule_belongs_to_user(rule: AlertRule | None, user_id: UUID) -> AlertRule:
    """ Valida existência e propriedade da regra antes de continuar """
    if not rule or rule.user_id != user_id:
        logger.warning("alert_rule_not_found", rule_id=str(rule.id) if rule else None, user_id=str(user_id))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra de alerta não encontrada",
        )
    return rule


def create_quick_alert_rule(db: Session, user: User, payload: QuickAlertRuleCreate) -> AlertRuleResponse:
    """ Cria regra simplificada para o usuário após validar o produto monitorado """
    logger.info("create_alert_rule_requested", user_id=str(user.id))

    _validate_monitored_product(db, payload.monitored_product_id, user.id)

    rule_data = AlertRuleCreate(
        user_id=user.id,
        monitored_product_id=payload.monitored_product_id,
        rule_type=payload.rule_type,
        enabled=True,
    )
    rule = create_alert_rule(db, rule_data)

    logger.info("alert_rule_created", rule_id=str(rule.id), user_id=str(user.id))
    return rule


def list_user_alert_rules(db: Session, user: User) -> list[AlertRuleResponse]:
    """ Lista todas as regras de alerta do usuário atual """
    logger.info("list_alert_rules_requested", user_id=str(user.id))
    rules = get_user_alert_rules(db, user.id)
    logger.info("list_alert_rules_completed", user_id=str(user.id), count=len(rules))
    return rules


def get_user_alert_rule(db: Session, user: User, rule_id: UUID) -> AlertRuleResponse:
    """ Recupera regra específica garantindo propriedade """
    logger.info("get_alert_rule_requested", user_id=str(user.id), rule_id=str(rule_id))
    rule = get_alert_rule(db, rule_id)
    validated = _ensure_rule_belongs_to_user(rule, user.id)
    logger.info("get_alert_rule_completed", user_id=str(user.id), rule_id=str(rule_id))
    return validated


def toggle_user_alert_rule(db: Session, user: User, rule_id: UUID, enabled: bool) -> AlertRuleResponse:
    """ Altera status da regra após validar existência e vínculo com o usuário """
    logger.info(
        "toggle_alert_rule_requested",
        user_id=str(user.id),
        rule_id=str(rule_id),
        enabled=enabled,
    )
    _ensure_rule_belongs_to_user(get_alert_rule(db, rule_id), user.id)
    updated = toggle_alert_rule(db, rule_id, enabled)
    logger.info("toggle_alert_rule_completed", user_id=str(user.id), rule_id=str(rule_id))
    return updated


def update_user_alert_rule(db: Session, user: User, rule_id: UUID, updates: AlertRuleUpdate) -> AlertRuleResponse:
    """ Atualiza campos da regra validando usuário e produto monitorado """
    logger.info("update_alert_rule_requested", user_id=str(user.id), rule_id=str(rule_id))

    rule = _ensure_rule_belongs_to_user(get_alert_rule(db, rule_id), user.id)

    if updates.user_id and updates.user_id != user.id:
        logger.warning(
            "alert_rule_invalid_user_change",
            rule_id=str(rule_id),
            requested_user=str(updates.user_id),
            owner_id=str(user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário inválido para a regra",
        )

    _validate_monitored_product(db, updates.monitored_product_id, user.id)

    updated_rule = update_alert_rule(db, rule_id, updates)
    logger.info("update_alert_rule_completed", user_id=str(user.id), rule_id=str(rule_id))
    return updated_rule


def delete_user_alert_rule(db: Session, user: User, rule_id: UUID) -> AlertRuleResponse:
    """ Remove uma regra do usuário após validar propriedade """
    logger.info("delete_alert_rule_requested", user_id=str(user.id), rule_id=str(rule_id))

    _ensure_rule_belongs_to_user(get_alert_rule(db, rule_id), user.id)
    deleted_rule = delete_alert_rule(db, rule_id)

    logger.info("delete_alert_rule_completed", user_id=str(user.id), rule_id=str(rule_id))
    return deleted_rule