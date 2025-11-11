""" Operações CRUD para produtos monitorados pelo sistema """

from typing import List, Optional, Tuple

from uuid import UUID
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo
from shared.utils.url_validation import normalize_product_url

from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.enums.enums_alerts import AlertType
from market_alert.schemas.schemas_alert_rules import AlertRuleCreate
from market_alert.crud import crud_alert_rules
from market_alert.crud import crud_price_history


def _normalize_for_lookup(product_url: str) -> str:
    """ Normaliza a URL para comparações internas tolerando entradas já sanitizadas """
    raw_value = str(product_url).strip()
    try:
        return normalize_product_url(raw_value)
    except ValueError:
        #Mantemos fallback em cado de dado legado que não respeita normalização
        return raw_value

def get_monitored_product_by_user_and_url(db: Session, user_id: UUID, product_url: str) -> MonitoredProduct | None:
    """ Busca produto específico combinando usuário e URL normalizada """

    normalized_url = _normalize_for_lookup(product_url)
    return (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user_id,
            MonitoredProduct.product_url == normalized_url,
        )
        .first()
    )

def create_pending_monitored_product(
    db: Session,
    user_id: UUID,
    name_identification: str,
    product_url: str,
) -> MonitoredProduct:
    """ Cria registro pendente garantindo unicidade por usuário e URL """

    normalized_url = _normalize_for_lookup(product_url)
    existing = get_monitored_product_by_user_and_url(db, user_id, normalized_url)

    if existing:
        if name_identification and existing.name_identification != name_identification:
            #Atualiza o nome quando o usuário reenfileira com identificação diferente
            existing.name_identification = name_identification
            db.commit()
            db.refresh(existing)
        return existing

    pending = MonitoredProduct(
        user_id=user_id,
        name_identification=name_identification,
        monitoring_type=MonitoringType.scraping,
        search_query=None,
        product_url=normalized_url,
        current_price=None,
        thumbnail=None,
        free_shipping=False,
        status=MonitoredStatus.pending,
        last_checked=None,
    )
    db.add(pending)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_retry = get_monitored_product_by_user_and_url(db, user_id, normalized_url)
        if existing_retry:
            return existing_retry
        raise
    db.refresh(pending)

    if pending.last_checked is not None:
        pending.last_checked = None
        db.commit()
        db.refresh(pending)
    return pending

def create_or_update_monitored_product_scraped(
    db: Session,
    user_id: UUID,
    product_data: MonitoredProductCreateScraping,
    scraped_info: MonitoredScrapedInfo,
    last_checked: datetime,
    *,
    currency: str | None = None,
    etag: str | None = None,
    last_modified: datetime | None = None,
) -> MonitoredProduct:
    """ Cria ou atualiza um produto monitorado a partir de dados de scraping """
    normalized_url = _normalize_for_lookup(product_data.product_url)
    #A URL chega validada pela API e é preservada para manter unicidade baseada na entrada do usuário

    #Verifica se o produto já existe para o usuário
    existing = get_monitored_product_by_user_and_url(db, user_id, normalized_url)

    if existing:
        if product_data.name_identification and existing.name_identification != product_data.name_identification:
            existing.name_identification = product_data.name_identification
        previous_price = existing.current_price
        existing.current_price = scraped_info.current_price
        existing.thumbnail = scraped_info.thumbnail
        existing.free_shipping = scraped_info.free_shipping
        existing.currency = currency or scraped_info.currency or existing.currency
        existing.etag = etag or existing.etag
        existing.last_modified = last_modified or existing.last_modified
        existing.last_checked = last_checked
        existing.status = MonitoredStatus.active
        db.commit()
        db.refresh(existing)

        if scraped_info.current_price is not None:
            crud_price_history.create_for_monitored(
                db,
                existing.id,
                scraped_info.current_price,
                currency or scraped_info.currency or existing.currency,
                last_checked,
            )
        existing._price_changed = previous_price != scraped_info.current_price
        return existing

    #Se não existir, cria o registro
    new = MonitoredProduct(
        user_id=user_id,
        name_identification=product_data.name_identification,
        search_query=None,
        product_url=normalized_url,
        current_price=scraped_info.current_price,
        thumbnail=scraped_info.thumbnail,
        free_shipping=scraped_info.free_shipping,
        monitoring_type=MonitoringType.scraping,
        status=MonitoredStatus.active,
        last_checked=last_checked,
        currency=currency or scraped_info.currency,
        etag=etag,
        last_modified=last_modified,
    )
    db.add(new)
    db.commit()
    db.refresh(new)

    if scraped_info.current_price is not None:
        crud_price_history.create_for_monitored(
            db,
            new.id,
            scraped_info.current_price,
            currency or scraped_info.currency,
            last_checked,
        )

    new._price_changed = True

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

def get_all_monitored_products(
    db: Session, 
    user_id: UUID, 
    monitoring_type: Optional[MonitoringType] = None,
) -> List[Tuple[MonitoredProduct, int]]:
    """ Retorna todos os produtos monitorados de um usuário com contagem de concorrentes """
    query = (
        db.query(
            MonitoredProduct,
            func.count(CompetitorProduct.id).label("competitors_count"),
        )
        .outerjoin(
            CompetitorProduct,
            MonitoredProduct.id == CompetitorProduct.monitored_product_id,
        )
        .filter(MonitoredProduct.user_id == user_id)
    )

    if monitoring_type:
        query = query.filter(MonitoredProduct.monitoring_type == monitoring_type)
    
    #Agrupa por todas as colunas para evitar resultados inconsistentes em bancos estritos como PostgreSQL
    query = query.group_by(*MonitoredProduct.__table__.c)
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
