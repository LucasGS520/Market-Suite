""" Operações CRUD para produtos monitorados pelo sistema """

from typing import List, Optional

from unicodedata import normalize
from uuid import UUID
from datetime import datetime

from sqlalchemy.orm import Session

from alert_app.models.models_products import MonitoredProduct
from utils.ml_url import canonicalize_ml_url
from alert_app.enums.enums_products import MonitoringType, MonitoredStatus
from alert_app.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo
from alert_app.enums.enums_alerts import AlertType
from alert_app.schemas.schemas_alert_rules import AlertRuleCreate
from alert_app.crud import crud_alert_rules


def create_or_update_monitored_product_scraped(db: Session, user_id: UUID, product_data: MonitoredProductCreateScraping, scraped_info: MonitoredScrapedInfo, last_checked: datetime) -> MonitoredProduct:
    """ Cria ou atualiza um produto monitorado a partir de dados de scraping """
    canonical = canonicalize_ml_url(str(product_data.product_url))
    normalized_url = canonical or str(product_data.product_url)

    #Verifica se o produto já existe para o usuário
    existing = (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user_id,
            MonitoredProduct.product_url == normalized_url
        )
        .first()
    )

    if existing:
        #Atualiza campos principais
        existing.current_price = scraped_info.current_price
        existing.thumbnail = scraped_info.thumbnail
        existing.free_shipping = scraped_info.free_shipping
        existing.last_checked = last_checked
        existing.status = MonitoredStatus.active
        db.commit()
        db.refresh(existing)
        return existing


    #Se não existir, cria o registro
    new = MonitoredProduct(
        user_id=user_id,
        name_identification=product_data.name_identification,
        search_query=None,
        product_url=normalized_url,
        target_price=product_data.target_price,
        current_price=scraped_info.current_price,
        thumbnail=scraped_info.thumbnail,
        free_shipping=scraped_info.free_shipping,
        monitoring_type=MonitoringType.scraping,
        status=MonitoredStatus.active,
        last_checked=last_checked
    )
    db.add(new)
    db.commit()
    db.refresh(new)

    #Se não houver regras ativas para este produto, cria um padrão
    rules = crud_alert_rules.get_active_alert_rules_for_product(db, user_id, new.id)
    if not rules:
        crud_alert_rules.create_alert_rule(
            db,
            AlertRuleCreate(
                user_id=user_id,
                monitored_product_id=new.id,
                rule_type=AlertType.PRICE_TARGET,
                enabled=True
            )
        )
    return new

def get_all_monitored_products(db: Session, user_id: UUID, monitoring_type: Optional[MonitoringType] = None) -> List[MonitoredProduct]:
    """ Retorna todos os produtos monitorados de um usuário """
    query = (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user_id
        )
    )

    if monitoring_type:
        query = query.filter(MonitoredProduct.monitoring_type == monitoring_type)
    return query.all()

def get_products_by_type(db: Session, monitoring_type: MonitoringType) -> List[MonitoredProduct]:
    """ Lista todos os produtos monitorados conforme o tipo """
    return (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.monitoring_type == monitoring_type
        )
        .all()
    )

def get_monitored_product_by_id(db: Session, product_id: UUID) -> Optional[MonitoredProduct]:
    """ Obtém um produto monitorado específico pelo ID """
    return (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.id == product_id
        )
        .first()
    )

def delete_monitored_product(db: Session, product_id: UUID) -> Optional[MonitoredProduct]:
    """ Remove um produto monitorado específico do banco de dados """
    product = get_monitored_product_by_id(db, product_id)
    if product:
        db.delete(product)
        db.commit()
    return product
