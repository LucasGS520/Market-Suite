""" Funções CRUD para manipular produtos concorrentes """
from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Sequence

import structlog
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo
from shared.utils import sanitize_text
from shared.utils.url_validation import normalize_competitor_url, normalize_product_url_for_storage

from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.enums.enums_products import ProductStatus, MonitoringType
from market_alert.crud import crud_price_history
from market_alert.domain.product_lifecycle import update_competitor_price_change_tracking
from market_alert.utils.name_derivation import derive_name_from_url, prepare_effective_name, should_replace_with_scraped
from market_alert.utils.price_utils import normalize_scraped_price, should_create_price_history
from market_alert.utils.price_decimal import to_decimal, different_price
from market_alert.utils.price_comparator import resolve_recompute_reason


logger = structlog.get_logger("crud_competitor")

def _normalize_competitor_storage_url(product_url: str) -> str:
    """ Normaliza URL de concorrente garantindo consistência com o armazenamento """
    normalized = normalize_competitor_url(product_url)
    if normalized:
        return normalized
    #Mantém um fallback mínimo para evitar escrita de URLs vazias no banco
    return str(product_url or "").strip()

def _resolve_scraped_availability_status(
    availability: bool | None,
    resolved_price: Decimal | None,
) -> tuple[bool | None, ProductStatus, bool]:
    """ Hrmoniza disponibilidade e status a partir do payload de scraping.

    A regra prioriza o preço como indicador de disponibilidade para evitar que
    concorrentes com preço válido sejam marcados como indisponíveis.
    """
    normalized_availability = availability
    if resolved_price is not None and availability in {None, False}:
        #Preço válido indica item disponível, mesmo com sinalização incompleta do scraper
        normalized_availability = True

    unavailable_by_data = resolved_price is None or normalized_availability is False
    status = ProductStatus.unavailable if unavailable_by_data else ProductStatus.available
    return normalized_availability, status, unavailable_by_data

def get_competitor_by_monitored_and_url(
    db: Session,
    monitored_product_id: UUID,
    product_url: str,
) -> CompetitorProduct | None:
    """ Recupera concorrente usando URL canônica vinculada ao monitorado """
    if not product_url:
        return None
    return (
        db.query(CompetitorProduct)
        .filter(
            CompetitorProduct.monitored_product_id == monitored_product_id,
            CompetitorProduct.product_url == product_url,
        )
        .first()
    )

def get_competitor_by_id(db: Session, competitor_id: UUID) -> CompetitorProduct | None:
    """ Recupera concorrente por ID com relacionamento do monitorado para autorização """
    return (
        db.query(CompetitorProduct)
        .join(MonitoredProduct)
        .filter(CompetitorProduct.id == competitor_id)
        .first()
    )

def update_competitors_pause_state(
    db: Session,
    monitored_product_id: UUID,
    *,
    is_paused: bool,
) -> int:
    """ Atualiza o estado de pausa de concorrentes vinculados a um monitorado """
    #Mantém concorrentes sincronizados com o monitorado sem alterar o fluxo de coleta
    updated = (
        db.query(CompetitorProduct)
        .filter(CompetitorProduct.monitored_product_id == monitored_product_id)
        .update({CompetitorProduct.is_paused: is_paused}, synchronize_session=False)
    )
    return int(updated or 0)

def update_competitor_pause_state(
    db: Session,
    competitor_id: UUID,
    *,
    is_paused: bool,
) -> bool:
    """ Atualiza o estado de pausa de um concorrente específico """
    updated = (
        db.query(CompetitorProduct)
        .filter(CompetitorProduct.id == competitor_id)
        .update({CompetitorProduct.is_paused: is_paused}, synchronize_session=False)
    )
    if updated:
        db.commit()
    return bool(updated)

def create_pending_competitor_product(
    db: Session,
    monitored_product_id: UUID,
    product_url: str,
    *,
    display_name: str | None = None,
    is_paused: bool | None = None,
) -> CompetitorProduct:
    """ Cria um concorrente pendente garantindo unicidade por monitorado e URL.

    O nome exibido é sanitizado quando fornecido manualmente, caso contrário,
    um rótulo é derivado da URL para evitar que o frontend exiba o ID bruto.
    Validações de negócio (pausa, URL duplicada, limites) são responsabilidade
    da camada de serviço antes de chamar esta função.
    """
    normalized_url = normalize_product_url_for_storage(str(product_url))
    if not normalized_url:
        normalized_url = _normalize_competitor_storage_url(str(product_url))

    resolved_is_paused = is_paused if is_paused is not None else False
    existing = get_competitor_by_monitored_and_url(db, monitored_product_id, normalized_url)

    if existing:
        return existing
    
    sanitized_display_name = sanitize_text(display_name) if display_name else None
    resolved_display_name = sanitized_display_name or derive_name_from_url(product_url, fallback="Concorrente pendente")

    pending = CompetitorProduct(
        monitored_product_id=monitored_product_id,
        name_competitor=resolved_display_name,
        product_url=normalized_url,
        current_price=None,
        old_price=None,
        free_shipping=False,
        seller=None,
        seller_rating=None,
        currency=None,
        thumbnail=None,
        status=ProductStatus.available,
        is_paused=resolved_is_paused,
        last_checked=None,
        last_scraped_at=None,
    )
    db.add(pending)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_retry = get_competitor_by_monitored_and_url(db, monitored_product_id, normalized_url)
        if existing_retry:
            return existing_retry
        raise

    db.refresh(pending)

    return pending

def count_competitors_by_monitored(db: Session, monitored_product_id: UUID, *, include_paused: bool = False) -> int:
    """ Conta quantos concorrentes estão associados ao monitorado informado """
    if not hasattr(db, "query"):
        return 0
    query = db.query(func.count(CompetitorProduct.id)).filter(
        CompetitorProduct.monitored_product_id == monitored_product_id,
    )
    if not include_paused:
        query = query.filter(CompetitorProduct.is_paused.is_(False))
    return int(query.scalar() or 0)
 
def create_or_update_competitor_product_scraped(
    db: Session,
    product_data: CompetitorProductCreateScraping,
    scraped_info: CompetitorScrapedInfo,
    last_checked: datetime,
    *,
    currency: str | None = None,
    etag: str | None = None,
    last_modified: datetime | None = None,
    collected_at: datetime | None = None,
) -> CompetitorProduct:
    """ Atualiza ou cria concorrente usando informações normalizadas do scraping """
    normalized_url = normalize_product_url_for_storage(str(product_data.product_url))
    if not normalized_url:
        normalized_url = _normalize_competitor_storage_url(product_data.product_url)

    checked_at = (
        last_checked.replace(tzinfo=timezone.utc)
        if last_checked.tzinfo is None
        else last_checked.astimezone(timezone.utc)
    )
    existing = get_competitor_by_monitored_and_url(
        db,
        product_data.monitored_product_id,
        normalized_url,
    )

    provided_name = (
        getattr(product_data, "name", None)
        or getattr(product_data, "display_name", None)
        or getattr(product_data, "name_identification", None)
    )
    resolved_name, fallback_name = prepare_effective_name(
        provided_name,
        scraped_info.name,
        normalized_url,
        fallback_name="Concorrente pendente",
    )

    if existing:
        return _persist_existing_competitor(
            db,
            existing,
            scraped_info=scraped_info,
            normalized_url=normalized_url,
            provided_name=provided_name,
            resolved_name=resolved_name,
            fallback_name=fallback_name,
            checked_at=checked_at,
            collected_at=collected_at,
            currency=currency,
            etag=etag,
            last_modified=last_modified,
        )

    return _persist_new_competitor(
        db,
        product_data=product_data,
        scraped_info=scraped_info,
        normalized_url=normalized_url,
        resolved_name=resolved_name,
        checked_at=checked_at,
        collected_at=collected_at,
        currency=currency,
        etag=etag,
        last_modified=last_modified,
    )

def _persist_existing_competitor(
    db: Session,
    existing: CompetitorProduct,
    *,
    scraped_info: CompetitorScrapedInfo,
    normalized_url: str,
    provided_name: str | None,
    resolved_name: str,
    fallback_name: str,
    checked_at: datetime,
    collected_at: datetime | None,
    currency: str | None,
    etag: str | None,
    last_modified: datetime | None,
) -> CompetitorProduct:
    """ Persiste atualização de concorrente existente com commit único. """
    resolved_price = normalize_scraped_price(scraped_info.current_price)
    existing._recompute_comparison = False
    existing._recompute_reason = None

    if provided_name and existing.name_competitor != resolved_name:
        existing.name_competitor = resolved_name
    elif should_replace_with_scraped(existing.name_competitor, fallback_name, scraped_info.name):
        existing.name_competitor = sanitize_text(scraped_info.name) or fallback_name
    elif existing.name_competitor is None:
        existing.name_competitor = resolved_name

    previous_price = existing.current_price
    previous_status = existing.status
    previous_last_checked = existing.last_checked
    previous_collected_at = existing.collected_at
    existing.old_price = existing.current_price
    last_status = scraped_info.last_status or existing.last_status
    resolved_availability, resolved_status, _ = _resolve_scraped_availability_status(
        scraped_info.availability,
        resolved_price,
    )
    if scraped_info.availability is False and resolved_price is not None:
        logger.info(
            "competitor_availability_overridden_by_price",
            product_id=str(existing.id),
            availability=scraped_info.availability,
            resolved_price=str(resolved_price),
        )

    price_changed = different_price(previous_price, resolved_price)
    availability_changed = previous_status != resolved_status
    resolved_currency = currency or scraped_info.currency or existing.currency
    collected_reference = collected_at or checked_at

    try:
        existing.current_price = resolved_price
        existing.thumbnail = scraped_info.thumbnail
        existing.free_shipping = scraped_info.free_shipping
        existing.currency = resolved_currency
        existing.etag = etag or existing.etag
        existing.last_modified = last_modified or existing.last_modified
        existing.last_checked = checked_at
        existing.last_scraped_at = collected_reference
        existing.collected_at = collected_reference
        existing.status = resolved_status
        existing.availability = resolved_availability
        existing.last_status = last_status
        existing.product_url = normalized_url

        history_allowed = should_create_price_history(resolved_price, resolved_availability)
        price_history_needed = price_changed and history_allowed
        if not history_allowed:
            logger.info(
                "product_marked_unavailable",
                product_id=str(existing.id),
                availability=resolved_availability,
                last_status=last_status,
                availability_inferred=resolved_availability is None,
                price_missing=resolved_price is None,
            )

        logger.info(
            "update_competitor_product_scraped",
            product_id=str(existing.id),
            previous_price=str(previous_price) if previous_price is not None else None,
            new_price=str(resolved_price) if resolved_price is not None else None,
            price_history_will_be_created=price_history_needed,
        )
        if price_history_needed:
            crud_price_history.create_for_competitor(
                db,
                existing.id,
                resolved_price,
                resolved_currency,
                checked_at,
            )

        update_competitor_price_change_tracking(
            existing,
            new_price=resolved_price,
            old_price=previous_price,
            collected_at=collected_reference,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(existing)
    existing._price_changed = price_changed
    existing._availability_changed = availability_changed
    recollection_refreshed = bool(
        previous_last_checked != existing.last_checked
        or previous_collected_at != existing.collected_at
    )
    enqueue_reason = resolve_recompute_reason(
        price_changed=existing._price_changed,
        availability_changed=existing._availability_changed,
        recollection_refreshed=recollection_refreshed,
    )
    if enqueue_reason:
        existing._recompute_comparison = True
        existing._recompute_reason = enqueue_reason

    logger.info(
        "updated_competitor",
        product_id=str(existing.id),
        price_changed=existing._price_changed,
        availability_changed=existing._availability_changed,
        enqueue_reason=enqueue_reason,
        recollection_refreshed=recollection_refreshed,
        last_checked=checked_at.isoformat(),
        availability=existing.availability,
        last_status=existing.last_status,
    )
    return existing

def _persist_new_competitor(
    db: Session,
    *,
    product_data: CompetitorProductCreateScraping,
    scraped_info: CompetitorScrapedInfo,
    normalized_url: str,
    resolved_name: str,
    checked_at: datetime,
    collected_at: datetime | None,
    currency: str | None,
    etag: str | None,
    last_modified: datetime | None,
) -> CompetitorProduct:
    """ Persiste criação de concorrente novo e seu histórico inicial. """
    resolved_price = normalize_scraped_price(scraped_info.current_price)
    resolved_currency = currency or scraped_info.currency
    resolved_availability, resolved_status, _ = _resolve_scraped_availability_status(
        scraped_info.availability,
        resolved_price,
    )
    if scraped_info.availability is False and resolved_price is not None:
        logger.info(
            "competitor_availability_overridden_by_price",
            product_id="pending",
            availability=scraped_info.availability,
            resolved_price=str(resolved_price),
        )
    
    collected_reference = collected_at or checked_at
    new = CompetitorProduct(
        monitored_product_id=product_data.monitored_product_id,
        name_competitor=resolved_name,
        product_url=normalized_url,
        current_price=resolved_price,
        old_price=to_decimal(scraped_info.old_price),
        free_shipping=scraped_info.free_shipping,
        seller=scraped_info.seller,
        seller_rating=scraped_info.seller_rating,
        thumbnail=scraped_info.thumbnail,
        status=resolved_status,
        last_checked=checked_at,
        last_scraped_at=checked_at,
        collected_at=collected_reference,
        currency=resolved_currency,
        etag=etag,
        last_modified=last_modified,
        availability=resolved_availability,
        last_status=scraped_info.last_status,
    )
    update_competitor_price_change_tracking(
        new,
        new_price=resolved_price,
        old_price=None,
        collected_at=collected_reference,
    )
    try:
        db.add(new)
        db.flush()
        history_allowed = should_create_price_history(resolved_price, resolved_availability)
        if not history_allowed:
            logger.info(
                "product_marked_unavailable",
                product_id=str(new.id),
                availability=resolved_availability,
                last_status=scraped_info.last_status,
                availability_inferred=resolved_availability is None,
                price_missing=resolved_price is None,
            )
        if resolved_price is not None and history_allowed:
            crud_price_history.create_for_competitor(
                db,
                new.id,
                resolved_price,
                resolved_currency,
                checked_at,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(new)
    new._price_changed = True
    new._availability_changed = True
    new._recompute_comparison = True
    new._recompute_reason = "material_change"
    return new

def get_all_competitor_products(db: Session, *, include_paused: bool = False) -> List[CompetitorProduct]:
    """ Retorna todos os produtos concorrentes cadastrados no banco """
    query = db.query(CompetitorProduct)
    if not include_paused:
        query = query.filter(CompetitorProduct.is_paused.is_(False))
    return query.all()

def get_competitor_products_by_user(db: Session, user_id: UUID) -> List[CompetitorProduct]:
    """ Lista os concorrentes pertencentes a determinado usuário """
    return (
        db.query(CompetitorProduct)
        .join(MonitoredProduct)
        .filter(MonitoredProduct.user_id == user_id)
        .all()
    )

def get_competitor_products_by_type(db: Session, user_id: UUID, monitoring_type: MonitoringType) -> List[CompetitorProduct]:
    """ Retorna todos os produtos concorrentes vinculados ao tipo do produto monitorado (API ou Scraping) """
    return (
        db.query(CompetitorProduct)
        .join(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user_id,
            MonitoredProduct.monitoring_type == monitoring_type
        ).all()
    )

def get_competitors_by_monitored_id(
    db: Session,
    monitored_product_id: UUID,
    *,
    include_paused: bool = False,
    include_inactive: bool = False,
) -> List[CompetitorProduct]:
    """ Lista concorrentes associados respeitando filtros de pausa e disponibilidade"""
    query = db.query(CompetitorProduct).filter(
        CompetitorProduct.monitored_product_id == monitored_product_id,
    )
    if not include_paused:
        #Evita enfileirar concorrentes pausados sem bloquear listagem administrativa
        query = query.filter(CompetitorProduct.is_paused.is_(False))

    if not include_inactive:
        #Garante que comparações automáticas não usem itens marcados como indisponíveis
        query = query.filter(
            CompetitorProduct.status.in_([ProductStatus.available, ProductStatus.pending]),
            CompetitorProduct.availability.isnot(False),
        )
    return query.all()

def delete_competitors_by_monitored_id(db: Session, monitored_product_id: UUID) -> List[UUID]:
    """ Remove concorrentes vinculados a um monitorado e retorna os IDs removidos """
    competitors = get_competitors_by_monitored_id(db, monitored_product_id, include_paused=True)
    deleted_ids: List[UUID] = []
    for item in competitors:
        deleted_ids.append(item.id)
        db.delete(item)
    db.commit()
    return deleted_ids

def delete_competitor(db: Session, competitor: CompetitorProduct) -> None:
    """ Remove concorrente específico garantindo flush para cascatas """
    db.delete(competitor)
    db.flush()

def paginate_competitors(
    db: Session,
    monitored_product_id: UUID,
    *,
    page: int,
    per_page: int,
    include_paused: bool = True,
    include_inactive: bool = True,
) -> tuple[int, int, int, List[CompetitorProduct]]:
    """ Retorna concorrentes paginados preservando contagens para a resposta """
    base_query = db.query(CompetitorProduct).filter(
        CompetitorProduct.monitored_product_id == monitored_product_id,
    )

    if not include_paused:
        base_query = base_query.filter(CompetitorProduct.is_paused.is_(False))

    if not include_inactive:
        base_query = base_query.filter(
            CompetitorProduct.status.in_([ProductStatus.available, ProductStatus.pending]),
            CompetitorProduct.availability.isnot(False),
            CompetitorProduct.current_price.isnot(None),
        )

    total = int(base_query.count())

    usable_query = base_query.filter(
        CompetitorProduct.current_price.isnot(None),
        CompetitorProduct.availability.isnot(False),
    )
    with_price_count = int(usable_query.count())
    excluded_due_to_inactive = max(total - with_price_count, 0)

    offset_value = max(page - 1, 0) * per_page
    items = (
        base_query.order_by(desc(CompetitorProduct.last_checked), CompetitorProduct.id)
        .offset(offset_value)
        .limit(per_page)
        .all()
    )

    return total, with_price_count, excluded_due_to_inactive, items
