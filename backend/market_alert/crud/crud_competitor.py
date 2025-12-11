""" Funções CRUD para manipular produtos concorrentes """
from __future__ import annotations

from uuid import UUID
from datetime import datetime
from typing import List, Sequence
from urllib.parse import unquote, urlparse

from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo
from shared.utils import sanitize_text
from shared.utils.url_validation import canonicalize_product_url, normalize_product_url_for_storage

from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.enums.enums_products import ProductStatus, MonitoringType
from market_alert.crud import crud_price_history

    
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

    #Verifica se já existe um concorrente com o mesmo monitorado e URL canônica
    existing = get_competitor_by_monitored_and_url(
        db,
        product_data.monitored_product_id,
        normalized_url,
    )

    if existing:
        #Atualiza somente campos relevantes
        previous_price = existing.current_price
        previous_status = existing.status
        existing.old_price = existing.current_price
        existing.current_price = scraped_info.current_price
        
        #Atualiza thumbnail, frete, moeda, etag, timestamps e status
        existing.thumbnail = scraped_info.thumbnail
        existing.free_shipping = scraped_info.free_shipping
        existing.currency = currency or scraped_info.currency or existing.currency
        existing.etag = etag or existing.etag
        existing.last_modified = last_modified or existing.last_modified
        existing.last_checked = last_checked
        existing.last_scraped_at = last_checked
        existing.status = ProductStatus.available
        existing.product_url = normalized_url
        
        #Sanitiza e persiste somente se tivermos um nome útil retornado pelo scraper.
        if getattr(scraped_info, "name", None):
            sanitized_name = sanitize_text(scraped_info.name)
            if sanitized_name:
                existing.name_competitor = sanitized_name
        
        db.commit()
        db.refresh(existing)

        if scraped_info.current_price is not None:
            crud_price_history.create_for_competitor(
                db,
                existing.id,
                scraped_info.current_price,
                currency or scraped_info.currency or existing.currency,
                last_checked,
            )
        existing._price_changed = previous_price != scraped_info.current_price
        existing._availability_changed = previous_status != ProductStatus.available
        return existing

    #Caso não exista, cria um registro
    new = CompetitorProduct(
        monitored_product_id=product_data.monitored_product_id,
        name_competitor=scraped_info.name,
        product_url=normalized_url,
        current_price=scraped_info.current_price,
        old_price=scraped_info.old_price,
        free_shipping=scraped_info.free_shipping,
        seller=scraped_info.seller,
        seller_rating=scraped_info.seller_rating,
        thumbnail=scraped_info.thumbnail,
        status=ProductStatus.available,
        last_checked=last_checked,
        last_scraped_at=last_checked,
        currency=currency or scraped_info.currency,
        etag=etag,
        last_modified=last_modified,
        )
    db.add(new)
    db.commit()
    db.refresh(new)
    if scraped_info.current_price is not None:
        crud_price_history.create_for_competitor(
            db,
            new.id,
            scraped_info.current_price,
            currency or scraped_info.currency,
            last_checked,
        )
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
    """ Lista todos os produtos concorrentes associados a um produto monitorado pelo ID """
    query = db.query(CompetitorProduct).filter(
        CompetitorProduct.monitored_product_id == monitored_product_id,
    )
    if not include_paused:
        query = query.filter(CompetitorProduct.is_paused.is_(False))
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
