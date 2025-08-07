""" Operações CRUD para regras de alerta """

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.models_alerts import AlertRule
from app.enums.enums_alerts import AlertType
from app.schemas.schemas_alert_rules import AlertRuleCreate
import app.metrics as metrics


def create_alert_rule(db: Session, rule_data: AlertRuleCreate) -> AlertRule:
    """ Cria uma regra de alerta no banco de dados """
    rule = AlertRule(
        user_id=rule_data.user_id,
        monitored_product_id=rule_data.monitored_product_id,
        rule_type=rule_data.rule_type,
        threshold_value=rule_data.threshold_value,
        threshold_percent=rule_data.threshold_percent,
        target_price=rule_data.target_price,
        product_status=rule_data.product_status,
        enabled=rule_data.enabled
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    #Incrementa métrica se a regra criada estiver habilitada
    try:
        if rule.enabled:
            metrics.ALERT_RULES_ACTIVE.inc()
    except Exception:
        pass
    return rule

def update_last_notified(db: Session, rule_id: UUID, notified_at: datetime | None = None) -> Optional[AlertRule]:
    """ Atualiza o campo ``last_notified_at`` de uma regra """
    if notified_at is None:
        notified_at = datetime.now(timezone.utc)
    return update_alert_rule(db, rule_id, {"last_notified_at": notified_at})

def get_alert_rule(db: Session, rule_id: UUID) -> Optional[AlertRule]:
    """ Recupera uma regra de alerta pelo "ID" """
    return db.query(AlertRule).filter(AlertRule.id == rule_id).first()

def get_user_alert_rules(db: Session, user_id: UUID) -> List[AlertRule]:
    """ Retorna todas as regras de alerta de um usuário """
    return db.query(AlertRule).filter(AlertRule.user_id == user_id).all()

def get_active_alert_rules_for_product(db: Session, user_id: UUID, monitored_product_id: UUID | None) -> List[AlertRule]:
    """ Retorna apenas as regras ativas para um usuário e produto """
    query = db.query(AlertRule).filter(AlertRule.user_id == user_id, AlertRule.enabled.is_(True))
    if monitored_product_id:
        query = query.filter(
            (AlertRule.monitored_product_id == monitored_product_id)
            | (AlertRule.monitored_product_id.is_(None))
        )
    else:
        query = query.filter(AlertRule.monitored_product_id.is_(None))
    return query.all()

def get_alert_rules_or_default(db: Session, user_id: UUID, monitored_product_id: UUID | None) -> List[AlertRule]:
    """ Retorna regras ativas ou uma regra padrão se nenhuma existir """
    rules = get_active_alert_rules_for_product(db, user_id, monitored_product_id)
    if rules:
        return rules

    return [
        AlertRule(
            user_id=user_id,
            monitored_product_id=monitored_product_id,
            rule_type=AlertType.PRICE_TARGET,
            enabled=True
        )
    ]

def toggle_alert_rule(db: Session, rule_id: UUID, enabled: bool) -> Optional[AlertRule]:
    """ Ativa ou desativa uma regra de alerta """
    rule = get_alert_rule(db, rule_id)
    if not rule:
        return None
    previous = rule.enabled
    rule.enabled = enabled
    db.commit()
    db.refresh(rule)

    #Ajusta o gauge apenas se o valor mudou
    try:
        if enabled and not previous:
            metrics.ALERT_RULES_ACTIVE.inc()
        elif not enabled and previous:
            metrics.ALERT_RULES_ACTIVE.dec()
    except Exception:
        pass
    return rule

def update_alert_rule(db: Session, rule_id: UUID, rule_update) -> Optional[AlertRule]:
    """ Atualiza campos de uma regra de alerta existente """
    rule = get_alert_rule(db, rule_id)
    if not rule:
        return None

    if hasattr(rule_update, "model_dump"):
        update_data = rule_update.model_dump(exclude_unset=True)
    elif isinstance(rule_update, dict):
        update_data = {k: v for k, v in rule_update.items() if v is not None}
    else:
        update_data = {k: v for k, v in vars(rule_update).items() if v is not None}

    prev_enabled = rule.enabled
    enabled_changed = False

    for key, value in update_data.items():
        if hasattr(rule, key):
            setattr(rule, key, value)
            if key == "enabled" and value != prev_enabled:
                enabled_changed = True

    db.commit()
    db.refresh(rule)

    if enabled_changed:
        try:
            if rule.enabled and not prev_enabled:
                metrics.ALERT_RULES_ACTIVE.inc()
            elif not rule.enabled and prev_enabled:
                metrics.ALERT_RULES_ACTIVE.dec()
        except Exception:
            pass

    return rule

def delete_alert_rule(db: Session, rule_id: UUID) -> Optional[AlertRule]:
    """ Remove uma regra de alerta do banco de dados """
    rule = get_alert_rule(db, rule_id)
    if rule:
        was_enabled = rule.enabled
        db.delete(rule)
        db.commit()

    try:
        if was_enabled:
            metrics.ALERT_RULES_ACTIVE.dec()
    except Exception:
        pass
    return rule
