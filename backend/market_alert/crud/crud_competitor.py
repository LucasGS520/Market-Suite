""" Funções CRUD para manipular produtos concorrentes """
from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Sequence
from urllib.parse import unquote, urlparse

import structlog
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo
from shared.utils import sanitize_text
from shared.utils.url_validation import canonicalize_product_url, normalize_product_url_for_storage
from shared.metrics.metrics_products import PRICE_HISTORY_SKIPPED_UNAVAILABLE_TOTAL

from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.enums.enums_products import ProductStatus, MonitoringType
from market_alert.crud import crud_price_history
from market_alert.utils.price_utils import normalize_scraped_price, should_create_price_history


logger = structlog.get_logger("crud_competitor")

def _to_decimal(value: Decimal | float | int | str | None) -> Decimal | None:
    """ Converte valor para `Decimal` preservando `None` e falhas de parsing """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    
def _different_price(previous_price: Decimal | float | int | str | None, current_price: Decimal | float | int | str | None) -> bool:
    """ Normaliza para `Decimal` antes de comparar e evitar falsos negativos """
    previous = _to_decimal(previous_price)
    current = _to_decimal(current_price)
    return previous != current

def get_competitor_by_monitored_and_url(
    db: Session,
    monitored_product_id: UUID,
    product_url: str,
) -> CompetitorProduct | None:
    """ Recupera concorrente usando URL canônica vinculada ao monitorado """
    normalized_url = normalize_product_url_for_storage(str(product_url))
    if not normalized_url:
        return None
    return (
        db.query(CompetitorProduct)
        .filter(
            CompetitorProduct.monitored_product_id == monitored_product_id,
            CompetitorProduct.product_url == normalized_url,
        )
        .first()
    )

def _derive_competitor_name_from_url(product_url: str) -> str:
    """Gera um nome provisório a partir da URL para preencher o cadastro pendente."""
    parsed = urlparse(product_url)
    caminho = unquote(parsed.path or "").strip("/")
    ultimo_segmento = caminho.split("/")[-1] if caminho else ""
    candidato = ultimo_segmento or parsed.netloc or str(product_url)
    normalizado = candidato.replace("-", " ").replace("_", " ").strip()
    sanitizado = sanitize_text(normalizado)

    if sanitizado:
        return sanitizado

    host = sanitize_text(parsed.netloc)
    if host:
        return host

    #Mantém um fallback amigável evitando valores vazios no banco
    return "Concorrente pendente"

def create_pending_competitor_product(
    db: Session,
    monitored_product_id: UUID,
    product_url: str,
    *,
    display_name: str | None = None,
) -> CompetitorProduct:
    """ Cria um concorrente pendente garantindo unicidade por monitorado e URL.
    
    O nome exibido é sanitizado quando fornecido manualmente, caso contrário, 
    um rótulo é derivado da URL para evitar que o frontend exiba o ID bruto.
    """
    normalized_url = normalize_product_url_for_storage(str(product_url))
    if not normalized_url:
        try:
            normalized_url = canonicalize_product_url(str(product_url))
        except ValueError:
            normalized_url = str(product_url).strip()
    existing = get_competitor_by_monitored_and_url(db, monitored_product_id, normalized_url)

    if existing:
        return existing
    
    sanitized_display_name = sanitize_text(display_name) if display_name else None
    resolved_display_name = sanitized_display_name or _derive_competitor_name_from_url(product_url)

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
        status=ProductStatus.pending,
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

    from market_alert.orchestrator.collector_service_orchestrator import enqueue_competitor_collection
    try:
        enqueue_competitor_collection(pending)
    except Exception:
        #Ignora falhas de enfileiramento para não quebrar a criação
        pass

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
) -> CompetitorProduct:
    """ Atualiza ou cria um produto concorrente a partir dos dados extraídos pelo scraping """
    normalized_url = normalize_product_url_for_storage(str(product_data.product_url))
    if not normalized_url:
        #Mantém fallback para registros antigos que já passaram pela validação externa
        try:
            normalized_url = canonicalize_product_url(str(product_data.product_url))
        except ValueError:
            normalized_url = str(product_data.product_url).strip()

    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)
    else:
        last_checked = last_checked.astimezone(timezone.utc)

    #Verifica se já existe um concorrente com o mesmo monitorado e URL canônica
    existing = get_competitor_by_monitored_and_url(
        db,
        product_data.monitored_product_id,
        normalized_url,
    )

    if existing:
        resolved_price = normalize_scraped_price(scraped_info.current_price)
        
        #Atualiza somente campos relevantes
        previous_price = existing.current_price
        previous_status = existing.status
        existing.old_price = existing.current_price
        availability = scraped_info.availability
        last_status = scraped_info.last_status or existing.last_status
        unavailable_by_data = availability is False or resolved_price is None

        price_changed = _different_price(previous_price, resolved_price)
        resolved_currency = currency or scraped_info.currency or existing.currency

        try:
            existing.current_price = resolved_price

            #Atualiza thumbnail, frete, moeda, etag, timestamps e status
            existing.thumbnail = scraped_info.thumbnail
            existing.free_shipping = scraped_info.free_shipping
            existing.currency = resolved_currency
            existing.etag = etag or existing.etag
            existing.last_modified = last_modified or existing.last_modified
            existing.last_checked = last_checked
            existing.last_scraped_at = last_checked
            existing.status = ProductStatus.unavailable if unavailable_by_data else ProductStatus.available
            existing.availability = availability
            existing.last_status = last_status
            existing.product_url = normalized_url

            #Sanitiza e persiste somente se tivermos um nome útil retornado pelo scraper.
            if getattr(scraped_info, "name", None):
                sanitized_name = sanitize_text(scraped_info.name)
                if sanitized_name:
                    existing.name_competitor = sanitized_name

            history_allowed = should_create_price_history(resolved_price, availability)
            price_history_needed = price_changed and history_allowed

            if not history_allowed:
                PRICE_HISTORY_SKIPPED_UNAVAILABLE_TOTAL.labels(owner="competitor").inc()
                logger.info(
                    "product_marked_unavailable",
                    product_id=str(existing.id),
                    availability=availability,
                    last_status=last_status,
                    availability_inferred=availability is None,
                    price_missing=resolved_price is None,
                )

            logger.info(
                "update_competitor_product_scraped",
                product_id=str(existing.id),
                previous_price=str(previous_price) if previous_price is not None else None,
                new_price=str(resolved_price) if resolved_price is not None else None,
                price_history_will_be_created=price_history_needed,
            )

            #Salvamos histórico junto ao commit do produto apenas quando houver alteração real
            if price_history_needed:
                crud_price_history.create_for_competitor(
                    db,
                    existing.id,
                    resolved_price,
                    resolved_currency,
                    last_checked,
                )

            db.commit()
        except Exception:
            #Rollback evita sessões sujas quando o chamador controla a transação externamente
            db.rollback()
            raise

        db.refresh(existing)
        existing._price_changed = price_changed
        existing._availability_changed = previous_status != existing.status

        logger.info(
            "updated_competitor",
            product_id=str(existing.id),
            price_changed=existing._price_changed,
            availability_changed=existing._availability_changed,
            last_checked=last_checked.isoformat(),
            availability=existing.availability,
            last_status=existing.last_status,
        )
        return existing

    #Caso não exista, cria um registro
    resolved_price = normalize_scraped_price(scraped_info.current_price)
    resolved_currency = currency or scraped_info.currency
    availability = scraped_info.availability
    last_status = scraped_info.last_status
    unavailable_by_data = availability is False or resolved_price is None
    
    new = CompetitorProduct(
        monitored_product_id=product_data.monitored_product_id,
        name_competitor=scraped_info.name,
        product_url=normalized_url,
        current_price=resolved_price,
        old_price=_to_decimal(scraped_info.old_price),
        free_shipping=scraped_info.free_shipping,
        seller=scraped_info.seller,
        seller_rating=scraped_info.seller_rating,
        thumbnail=scraped_info.thumbnail,
        status=ProductStatus.unavailable if unavailable_by_data else ProductStatus.available,
        last_checked=last_checked,
        last_scraped_at=last_checked,
        currency=resolved_currency,
        etag=etag,
        last_modified=last_modified,
        availability=availability,
        last_status=last_status,
        )
    try:
        db.add(new)
        db.flush()
        history_allowed = should_create_price_history(resolved_price, availability)
        if not history_allowed:
            PRICE_HISTORY_SKIPPED_UNAVAILABLE_TOTAL.labels(owner="competitor").inc()
            logger.info(
                "product_marked_unavailable",
                product_id=str(new.id),
                availability=availability,
                last_status=last_status,
                availability_inferred=availability is None,
                price_missing=resolved_price is None,
            )
        if resolved_price is not None and history_allowed:
            crud_price_history.create_for_competitor(
                db,
                new.id,
                resolved_price,
                resolved_currency,
                last_checked,
            )
        db.commit()
    except Exception:
        #Rollback mantém atomicidade entre criação do concorrente e histórico de preços
        db.rollback()
        raise

    db.refresh(new)
    new._price_changed = True
    new._availability_changed = True
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
) -> List[CompetitorProduct]:
    """ Lista concorrentes associados respeitando filtros de pausa e disponibilidade"""
    query = db.query(CompetitorProduct).filter(
        CompetitorProduct.monitored_product_id == monitored_product_id,
    )
    if not include_paused:
        #Evita enfileirar ou listar concorrentes pausados ou já indisponíveis
        query = query.filter(
            CompetitorProduct.is_paused.is_(False),
            CompetitorProduct.status.in_(
                [ProductStatus.available, ProductStatus.pending]
            ),
        )
    return query.all()

def delete_competitors_by_monitored_id(db: Session, monitored_product_id: UUID) -> List[CompetitorProduct]:
    """ Remove todos os produtos concorrentes vinculados a um produto monitorado """
    competitors = get_competitors_by_monitored_id(db, monitored_product_id, include_paused=True)
    for item in competitors:
        db.delete(item)
    db.commit()
    return competitors

def paginate_competitors(
    db: Session,
    monitored_product_id: UUID,
    *,
    page: int,
    per_page: int,
    include_paused: bool = False,
) -> tuple[int, List[CompetitorProduct]]:
    """ Retorna concorrentes paginados usando apenas filtros essenciais. """
    query = db.query(CompetitorProduct).filter(
        CompetitorProduct.monitored_product_id == monitored_product_id,
    )

    query = query.filter(
        CompetitorProduct.status != ProductStatus.pending,
        CompetitorProduct.current_price.isnot(None),
    )

    if not include_paused:
        query = query.filter(CompetitorProduct.is_paused.is_(False))

    total = int(query.count())

    offset_value = max(page - 1, 0) * per_page
    items = (
        query.order_by(desc(CompetitorProduct.last_checked), CompetitorProduct.id)
        .offset(offset_value)
        .limit(per_page)
        .all()
    )

    return total, items
