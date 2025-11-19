""" Operações CRUD para produtos monitorados pelo sistema """

from typing import List, Optional, Tuple

from uuid import UUID
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.shared.schemas.shared_schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo
from shared.utils import sanitize_text
from shared.utils.url_validation import normalize_product_url_for_storage

from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.enums.enums_alerts import AlertType
from market_alert.schemas.schemas_alert_rules import AlertRuleCreate
from market_alert.crud import crud_alert_rules
from market_alert.crud import crud_price_history


def _derive_name_from_url(product_url: str) -> str:
    """ Extrai um identificador legível da URL quando o usuário não fornece nome """
    parsed = urlparse(product_url)
    #Utiliza o último segmento do path como base do nome
    path_segment = unquote(parsed.path or "").strip("/")
    last_piece = path_segment.split("/")[-1] if path_segment else ""
    candidate = last_piece or parsed.netloc or str(product_url)
    normalized = candidate.replace("-", " ").replace("_", " ").strip()
    sanitized = sanitize_text(normalized)
    if sanitized:
        return sanitized
    host = sanitize_text(parsed.netloc)
    if host:
        return host
    #Fallback amigável para evitar persistir string vazia
    return "Produto monitorado"

def _prepare_effective_name(
    provided_name: str | None,
    scraped_name: str | None,
    product_url: str,
) -> tuple[str, str]:
    """ Determina o nome final aplicando prioridade usuário → scraping → URL """
    fallback = _derive_name_from_url(product_url)
    sanitized_scraped = sanitize_text(scraped_name)
    if provided_name:
        return provided_name, fallback
    if sanitized_scraped:
        return sanitized_scraped, fallback
    return fallback, fallback

def _should_replace_with_scraped(
    existing_name: str | None,
    fallback_name: str,
    scraped_name: str | None,
) -> bool:
    """ Decide se devemos substituir nome atual pela identificação vinda do scraping """
    sanitized_scraped = sanitize_text(scraped_name)
    if not sanitized_scraped:
        return False
    if existing_name is None:
        return True
    return existing_name.strip().casefold() == fallback_name.strip().casefold()

def get_monitored_product_by_user_and_url(db: Session, user_id: UUID, product_url: str) -> MonitoredProduct | None:
    """ Busca produto específico combinando usuário e URL normalizada """

    normalized_url = normalize_product_url_for_storage(product_url)
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
    name_identification: str | None,
    product_url: str,
) -> MonitoredProduct:
    """ Cria registro pendente garantindo unicidade por usuário e URL """

    normalized_url = normalize_product_url_for_storage(product_url)
    existing = get_monitored_product_by_user_and_url(db, user_id, normalized_url)

    if existing:
        if name_identification and existing.name_identification != name_identification:
            #Atualiza o nome quando o usuário reenfileira com identificação diferente
            existing.name_identification = name_identification
            db.commit()
            db.refresh(existing)
        return existing
    
    effective_name, _ = _prepare_effective_name(
        name_identification,
        scraped_name=None,
        product_url=normalized_url,
    )

    #Substituímos o nome derivado da URL apenas após o scraping devolver informação confiável
    pending = MonitoredProduct(
        user_id=user_id,
        name_identification=effective_name,
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
    scraped_name: str | None = None,
) -> MonitoredProduct:
    """ Cria ou atualiza um produto monitorado a partir de dados de scraping """
    normalized_url = normalize_product_url_for_storage(product_data.product_url)
    #A URL chega validada pela API e é preservada para manter unicidade baseada na entrada do usuário

    #Verifica se o produto já existe para o usuário
    existing = get_monitored_product_by_user_and_url(db, user_id, normalized_url)

    resolved_name, fallback_name = _prepare_effective_name(
        product_data.name_identification,
        scraped_name,
        normalized_url,
    )

    if existing:
        if product_data.name_identification and existing.name_identification != product_data.name_identification:
            existing.name_identification = product_data.name_identification
        elif _should_replace_with_scraped(existing.name_identification, fallback_name, scraped_name):
            #Substituímos o placeholder por nome real vindo do scraping
            existing.name_identification = sanitize_text(scraped_name) or fallback_name
        elif existing.name_identification is None:
            existing.name_identification = resolved_name
        previous_price = existing.current_price
        previous_status = existing.status
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
        existing._availability_changed = previous_status != MonitoredStatus.active
        return existing

    #Se não existir, cria o registro
    new = MonitoredProduct(
        user_id=user_id,
        name_identification=resolved_name,
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
    new._availability_changed = True

    #Se não houver regras ativas para este produto, cria um padrão
    rules = crud_alert_rules.get_active_alert_rules_for_product(db, user_id, new.id)
    if not rules:
        crud_alert_rules.create_alert_rule(
            db,
            AlertRuleCreate(
                user_id=user_id,
                monitored_product_id=new.id,
                rule_type=AlertType.PRICE_CHANGE,
                enabled=True
            )
        )
    return new

def get_all_monitored_products(
    db: Session,
    user_id: UUID,
    monitoring_type: Optional[MonitoringType] = None,
    *,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[tuple[MonitoredProduct, int]], int]:
    """ Retorna produtos monitorados com contagem de concorrentes e suporte a paginação """
    normalized_page = max(page, 1)
    normalized_per_page = max(per_page, 1)

    base_query = db.query(MonitoredProduct).filter(MonitoredProduct.user_id == user_id)
    if monitoring_type:
        base_query = base_query.filter(MonitoredProduct.monitoring_type == monitoring_type)

    total = base_query.count()
    if total == 0:
        return [], 0

    offset = (normalized_page - 1) * normalized_per_page
    products = (
        base_query.order_by(MonitoredProduct.created_at.desc())
        .offset(offset)
        .limit(normalized_per_page)
        .all()
    )

    if not products:
        return [], total
    product_ids = [product.id for product in products]

    competitor_rows = (
        db.query(
            CompetitorProduct.monitored_product_id,
            func.count(CompetitorProduct.id).label("competitors_count"),
        )
        .filter(CompetitorProduct.monitored_product_id.in_(product_ids))
        .group_by(CompetitorProduct.monitored_product_id)
        .all()
    )
    competitors_map = {
        row.monitored_product_id: int(row.competitors_count) for row in competitor_rows
    }

    items = [(product, competitors_map.get(product.id, 0)) for product in products]
    return items, total

def get_featured_monitored_products(
    db: Session,
    user_id: UUID,
    *,
    limit: int = 3,
) -> list[MonitoredProduct]:
    """ Seleciona produtos em destaque respeitando limite máximo configurado """
    normalized_limit = max(0, limit)
    if normalized_limit == 0:
        return []
    
    base_query = (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user_id,
            MonitoredProduct.current_price.isnot(None),
        )
    )

    #Prioriza itens marcados manualmente como destaque
    manual_featured = (
        base_query.filter(MonitoredProduct.is_featured.is_(True))
        .order_by(MonitoredProduct.updated_at.desc())
        .limit(normalized_limit)
        .all()
    )
    if len(manual_featured) >= normalized_limit:
        return manual_featured[:normalized_limit]
    
    remaining_limit = normalized_limit - len(manual_featured)
    excluded_ids = [product.id for product in manual_featured]
    fallback_query = base_query.filter(MonitoredProduct.status == MonitoredStatus.active)
    if excluded_ids:
        fallback_query = fallback_query.filter(~MonitoredProduct.id.in_(excluded_ids))

    #Complementa com itens mais recentes caso falte destaque manual
    fallback_featured = (
        fallback_query
        .order_by(
            MonitoredProduct.last_checked.desc(),
            MonitoredProduct.created_at.desc(),
        )
        .limit(remaining_limit)
        .all()
    )
    return manual_featured + fallback_featured

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

def mark_monitored_product_failed(
    db: Session,
    product_id: UUID,
    *,
    touched_at: datetime | None = None,
) -> MonitoredProduct | None:
    """ Atualiza o status de um produto monitorado para ``failed`` registrando o último contato """
    product = get_monitored_product_by_id(db, product_id)
    if product is None:
        return None
    
    product.status = MonitoredStatus.failed
    product.last_checked = touched_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(product)
    return product
