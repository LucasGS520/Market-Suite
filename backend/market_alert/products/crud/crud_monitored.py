""" Funções CRUD para produtos monitorados pelo sistema """

from uuid import UUID
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

import structlog
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from shared.schemas.shared_schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo
from shared.scheduling import EVENT_RESUMED, EVENT_STANDARD
from shared.utils import sanitize_text
from shared.utils.url_validation import normalize_product_url_for_storage

from market_alert.models import User
from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.models.models_comparisons import PriceComparisonSummary
from market_alert.models.models_price_history import PriceHistory
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.enums.enums_comparisons import CompetitivenessStatus
import market_alert.products.crud.crud_competitor as crud_competitor
import market_alert.products.crud.crud_price_history as crud_price_history
from market_alert.products.domain.product_lifecycle import (
    compute_next_check_at,
    resolve_scheduling_event,
    update_price_change_tracking,
)
from market_alert.products.utils.name_derivation import prepare_effective_name, should_replace_with_scraped
from market_alert.products.utils.price_utils import normalize_scraped_price, should_create_price_history
from market_alert.products.utils.price_decimal import different_price


logger = structlog.get_logger("crud_monitored")

def _ensure_monitored_access(db: Session, monitored_id: UUID, user: User) -> MonitoredProduct:
    """ Obtém monitorado garantindo posse do usuário """
    product = get_monitored_product_by_id(db, monitored_id)
    if product is None:
        raise MonitoredNotFoundError("Monitorado não encontrado")
    if product.user_id != user.id:
        raise MonitoredOwnershipError("Usuário sem permissão para este monitorado")
    return product

class MonitoredOwnershipError(PermissionError):
    """ Erro lançado quando o usuário não possui acesso ao monitorado"""

class MonitoredNotFoundError(LookupError):
    """ Erro lançado quando o monitorado não é localizado"""

class MonitoredLockError(RuntimeError):
    """ Erro lançado quando o lock exclusivo não pode ser adquirido"""

def _resolve_availability(
    scraped_availability: bool | None, last_status: str | None
) -> bool | None:
    """ Determina disponibilidade priorizando sinais de indisponibilidade """
    unavailable_statuses = {"unavailable", "removed", "sold_out"}
    normalized_status = (last_status or "").strip().lower()
    if normalized_status in unavailable_statuses:
        return False
    return scraped_availability

def get_monitored_product_by_user_and_url(db: Session, user_id: UUID, product_url: str) -> MonitoredProduct | None:
    """ Busca produto específico combinando usuário e URL normalizada """

    normalized_url = normalize_product_url_for_storage(product_url)
    return (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user_id,
            MonitoredProduct.normalized_url == normalized_url,
        )
        .first()
    )

def get_last_price_change_for_monitored(db: Session, monitored_product_id: UUID) -> datetime | None:
    """ Retorna a última mudança de preço considerando monitorado e concorrentes

    A criação de ``PriceHistory`` é condicionada a alterações reais de preço
    tanto do item monitorado quanto dos concorrentes. Assim, ao buscar o
    ``checked_at`` mais recente entre esses registros, obtemos o último evento
    efetivo de alteração de preço no ecossistema do produto, evitando leituras
    duplicadas.
    """
    competitor_subquery = (
        db.query(CompetitorProduct.id)
        .filter(CompetitorProduct.monitored_product_id == monitored_product_id)
        .subquery()
    )
    latest_change = (
        db.query(func.max(PriceHistory.checked_at))
        .filter(
            or_(
                PriceHistory.monitored_product_id == monitored_product_id,
                PriceHistory.competitor_product_id.in_(competitor_subquery),
            )
        )
        .scalar()
    )

    if latest_change and latest_change.tzinfo is None:
        return latest_change.replace(tzinfo=timezone.utc)
    return latest_change

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
    
    effective_name, _ = prepare_effective_name(
        name_identification,
        None,
        normalized_url,
        fallback_label="Produto pendente",
    )

    #Substituímos o nome derivado da URL apenas após o scraping devolver informação confiável
    pending = MonitoredProduct(
        user_id=user_id,
        name_identification=effective_name,
        monitoring_type=MonitoringType.scraping,
        search_query=None,
        product_url=normalized_url,
        normalized_url=normalized_url,
        current_price=None,
        thumbnail=None,
        free_shipping=False,
        status=MonitoredStatus.pending,
        last_checked=None,
        next_check_at=None,
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
    collected_at: datetime | None = None,
) -> MonitoredProduct:
    """ Cria ou atualiza um monitorado a partir do payload consolidade de scraping """
    normalized_url = normalize_product_url_for_storage(product_data.product_url)
    checked_at = (
        last_checked.replace(tzinfo=timezone.utc)
        if last_checked.tzinfo is None
        else last_checked.astimezone(timezone.utc)
    )

    existing = get_monitored_product_by_user_and_url(db, user_id, normalized_url)
    resolved_name, fallback_name = prepare_effective_name(
        product_data.name_identification,
        scraped_name,
        normalized_url,
        fallback_label="Produto pendente",
    )

    if existing is not None:
        return _persist_existing_monitored(
            db,
            existing,
            product_data=product_data,
            scraped_info=scraped_info,
            normalized_url=normalized_url,
            resolved_name=resolved_name,
            fallback_name=fallback_name,
            scraped_name=scraped_name,
            checked_at=checked_at,
            collected_at=collected_at,
            currency=currency,
            etag=etag,
            last_modified=last_modified,
        )

    return _persist_new_monitored(
        db,
        user_id=user_id,
        scraped_info=scraped_info,
        normalized_url=normalized_url,
        resolved_name=resolved_name,
        checked_at=checked_at,
        collected_at=collected_at,
        currency=currency,
        etag=etag,
        last_modified=last_modified,
    )

def _persist_existing_monitored(
    db: Session,
    existing: MonitoredProduct,
    *,
    product_data: MonitoredProductCreateScraping,
    scraped_info: MonitoredScrapedInfo,
    normalized_url: str,
    resolved_name: str,
    fallback_name: str,
    scraped_name: str | None,
    checked_at: datetime,
    collected_at: datetime | None,
    currency: str | None,
    etag: str | None,
    last_modified: datetime | None,
) -> MonitoredProduct:
    """ Persiste atualização de monitorado existente em transação única. """
    resolved_price = normalize_scraped_price(scraped_info.current_price)
    availability = _resolve_availability(scraped_info.availability, scraped_info.last_status)
    last_status = scraped_info.last_status or existing.last_status
    inactive_due_to_data = availability is False or resolved_price is None
    collected_reference = collected_at or checked_at

    if product_data.name_identification and existing.name_identification != product_data.name_identification:
        existing.name_identification = product_data.name_identification
    elif should_replace_with_scraped(existing.name_identification, fallback_name, scraped_name):
        existing.name_identification = sanitize_text(scraped_name) or fallback_name
    elif existing.name_identification is None:
        existing.name_identification = resolved_name

    previous_price = existing.current_price
    previous_status = existing.status
    price_changed = different_price(previous_price, resolved_price)
    resolved_currency = currency or scraped_info.currency or existing.currency

    logger.info(
        "monitored_commit_preview",
        product_id=str(existing.id),
        availability=availability,
        last_status=last_status,
        resolved_price=str(resolved_price) if resolved_price is not None else None,
        price_changed=price_changed,
    )

    try:
        existing.current_price = resolved_price
        existing.thumbnail = scraped_info.thumbnail
        existing.free_shipping = scraped_info.free_shipping
        existing.currency = resolved_currency
        existing.etag = etag or existing.etag
        existing.last_modified = last_modified or existing.last_modified
        existing.last_checked = checked_at
        existing.last_scraped_at = checked_at
        existing.collected_at = collected_reference
        existing.status = MonitoredStatus.inactive if inactive_due_to_data else MonitoredStatus.active
        existing.availability = availability
        existing.last_status = last_status
        existing.normalized_url = normalized_url

        history_allowed = should_create_price_history(resolved_price, availability)
        price_history_needed = price_changed and history_allowed
        if not history_allowed:
            logger.info(
                "product_marked_unavailable",
                product_id=str(existing.id),
                availability=availability,
                last_status=last_status,
                availability_inferred=availability is None,
                price_missing=resolved_price is None,
            )
        
        logger.info(
            "updated_monitored_product_scraped",
            product_id=str(existing.id),
            previous_price=str(previous_price) if previous_price is not None else None,
            new_price=str(resolved_price) if resolved_price is not None else None,
            price_history_will_be_created=price_history_needed,
        )
        if price_history_needed:
            crud_price_history.create_for_monitored(
                db,
                existing.id,
                resolved_price,
                resolved_currency,
                checked_at,
            )

        update_price_change_tracking(
            existing,
            new_price=resolved_price,
            old_price=previous_price,
            collected_at=collected_reference,
        )
        availability_changed = previous_status != existing.status
        schedule_event = resolve_scheduling_event(
            price_changed=price_changed,
            availability_changed=availability_changed,
        )
        schedule_decision = compute_next_check_at(
            existing,
            reference_time=checked_at,
            event_type=schedule_event,
        )
        existing.stability_score = schedule_decision.stability_score
        existing.next_check_at = schedule_decision.next_check_at
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(existing)
    existing._price_changed = price_changed
    existing._availability_changed = previous_status != existing.status
    existing._recompute_comparison = bool(existing._price_changed or existing._availability_changed)
    existing._recompute_reason = "material_change" if existing._recompute_comparison else None

    logger.info(
        "updated_monitored",
        product_id=str(existing.id),
        price_changed=existing._price_changed,
        availability_changed=existing._availability_changed,
        last_checked=checked_at.isoformat(),
        availability=existing.availability,
        last_status=existing.last_status,
    )
    return existing

def _persist_new_monitored(
    db: Session,
    *,
    user_id: UUID,
    scraped_info: MonitoredScrapedInfo,
    normalized_url: str,
    resolved_name: str,
    checked_at: datetime,
    collected_at: datetime | None,
    currency: str | None,
    etag: str | None,
    last_modified: datetime | None,
) -> MonitoredProduct:
    """ Persiste criação de monitorado novo e histórico inicial. """
    resolved_price = normalize_scraped_price(scraped_info.current_price)
    resolved_currency = currency or scraped_info.currency
    availability = _resolve_availability(scraped_info.availability, scraped_info.last_status)
    inactive_due_to_data = availability is False or resolved_price is None
    collected_reference = collected_at or checked_at

    new = MonitoredProduct(
        user_id=user_id,
        name_identification=resolved_name,
        search_query=None,
        product_url=normalized_url,
        normalized_url=normalized_url,
        current_price=resolved_price,
        thumbnail=scraped_info.thumbnail,
        free_shipping=scraped_info.free_shipping,
        monitoring_type=MonitoringType.scraping,
        status=MonitoredStatus.inactive if inactive_due_to_data else MonitoredStatus.active,
        last_checked=checked_at,
        last_scraped_at=checked_at,
        collected_at=collected_reference,
        next_check_at=None,
        currency=resolved_currency,
        etag=etag,
        last_modified=last_modified,
        availability=availability,
        last_status=scraped_info.last_status,
    )
    update_price_change_tracking(
        new,
        new_price=resolved_price,
        old_price=None,
        collected_at=collected_reference,
    )
    initial_schedule = compute_next_check_at(
        new,
        reference_time=checked_at,
        event_type=EVENT_STANDARD,
    )
    new.stability_score = initial_schedule.stability_score
    new.next_check_at = initial_schedule.next_check_at
    
    try:
        db.add(new)
        db.flush()
        history_allowed = should_create_price_history(resolved_price, availability)
        if not history_allowed:
            logger.info(
                "product_marked_unavailable",
                product_id=str(new.id),
                availability=availability,
                last_status=scraped_info.last_status,
                availability_inferred=availability is None,
                price_missing=resolved_price is None,
            )
        if resolved_price is not None and history_allowed:
            crud_price_history.create_for_monitored(
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

def _join_latest_summary(query, db: Session):
    """ Acopla o último resumo disponível para permitir filtros de competitividade """
    latest_summary_subquery = (
        db.query(
            PriceComparisonSummary.monitored_product_id.label("monitored_product_id"),
            func.max(PriceComparisonSummary.timestamp).label("max_timestamp"),
        )
        .group_by(PriceComparisonSummary.monitored_product_id)
        .subquery()
    )
    summary_alias = aliased(PriceComparisonSummary)
    joined_query = (
        query.join(
            latest_summary_subquery,
            latest_summary_subquery.c.monitored_product_id == MonitoredProduct.id,
        )
        .join(
            summary_alias,
            (
                summary_alias.monitored_product_id
                == latest_summary_subquery.c.monitored_product_id
            )
            & (summary_alias.timestamp == latest_summary_subquery.c.max_timestamp),
        )
    )
    return joined_query, summary_alias

def get_all_monitored_products(
    db: Session,
    user_id: UUID,
    monitoring_type: Optional[MonitoringType] = None,
    *,
    page: int = 1,
    per_page: int | None = None,
    query: str | None = None,
    status: CompetitivenessStatus | None = None,
) -> tuple[list[tuple[MonitoredProduct, int]], int, int]:
    """ Lista produtos monitorados com filtros avançados e contagem de concorrentes.

    Aceita `per_page=None` para retornar todos os itens disponíveis, mantendo um teto
    defensivo quando o parâmetro é enviado e preservando ordenação determinística
    para evitar variações entre chamadas paginadas.
    """
    normalized_page = max(page, 1)
    max_per_page = 200
    apply_pagination = per_page is not None
    normalized_per_page = None if per_page is None else min(max(per_page, 1), max_per_page)

    base_query = db.query(MonitoredProduct).filter(
        MonitoredProduct.user_id == user_id,
    )
    if monitoring_type:
        base_query = base_query.filter(MonitoredProduct.monitoring_type == monitoring_type)

    if query and query.strip():
        like_pattern = f"%{query.strip()}%"
        base_query = base_query.filter(
            or_(
                MonitoredProduct.name_identification.ilike(like_pattern),
                MonitoredProduct.search_query.ilike(like_pattern),
            )
        )

    if status is not None:
        base_query, summary_alias = _join_latest_summary(base_query, db)
        dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
        dialect_key = getattr(dialect_name, "name", "") if dialect_name else ""
        if dialect_key == "sqlite":
            status_field = func.json_extract(
                summary_alias.aggregates,
                "$.competitiveness_status",
            )
        else:
            status_field = func.json_extract_path_text(
                summary_alias.aggregates,
                "competitiveness_status",
            )
        base_query = base_query.filter(status_field == status.value)

    total = base_query.count()
    if total == 0:
        return [], 0, 0

    ordered_query = base_query.order_by(
        MonitoredProduct.created_at.desc(),
        MonitoredProduct.id.desc(),
    )
    if apply_pagination and normalized_per_page:
        offset = (normalized_page - 1) * normalized_per_page
        ordered_query = ordered_query.offset(offset).limit(normalized_per_page)

    products = ordered_query.all()

    if not products:
        resolved_per_page = normalized_per_page if apply_pagination and normalized_per_page else 0
        return [], total, resolved_per_page
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
    resolved_per_page = normalized_per_page if apply_pagination and normalized_per_page else len(items)
    return items, total, resolved_per_page

def get_featured_monitored_products(
    db: Session,
    user_id: UUID,
    *,
    limit: int = 3,
) -> list[MonitoredProduct]:
    """ Seleciona produtos em destaque combinando critérios de prioridade """
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

    fallback_candidates = fallback_query.all()
    if not fallback_candidates:
        return manual_featured

    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    #Mapeia o preço mais recente coletado há pelo menos 24h para calcular a variação
    candidate_ids = [product.id for product in fallback_candidates]

    baseline_rows = (
        db.query(
            PriceHistory.monitored_product_id,
            PriceHistory.price,
        )
        .filter(
            PriceHistory.monitored_product_id.in_(candidate_ids),
            PriceHistory.checked_at <= cutoff_24h,
        )
        .order_by(
            PriceHistory.monitored_product_id,
            PriceHistory.checked_at.desc(),
        )
        .all()
    )

    baseline_map: dict[UUID, Decimal] = {}
    for row in baseline_rows:
        if row.monitored_product_id not in baseline_map:
            baseline_map[row.monitored_product_id] = row.price

    def _variation_24h(product: MonitoredProduct) -> Decimal:
        """ Calcula variação percentual aproximada em 24h para ordenação """

        reference = baseline_map.get(product.id)
        if reference is None:
            return Decimal("0")
        try:
            if reference == 0:
                return Decimal("0")
            return abs((product.current_price - reference) / reference)
        except (InvalidOperation, TypeError, ZeroDivisionError):
            return Decimal("0")

    scored_candidates = sorted(
        fallback_candidates,
        key=lambda product: (
            _variation_24h(product),
            product.created_at or datetime.now(timezone.utc),
        ),
        reverse=True,
    )

    fallback_featured = scored_candidates[:remaining_limit]
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

def pause_monitored(db: Session, monitored_id: UUID, user: User) -> MonitoredProduct:
    """ Pausa monitorado de forma idempotente e sincroniza a fila contínua """
    monitored = _ensure_monitored_access(db, monitored_id, user)
    now = datetime.now(timezone.utc)
    was_paused = bool(monitored.paused)

    if not was_paused:
        monitored.paused = True
        monitored.paused_at = now

    competitors_updated = crud_competitor.update_competitors_pause_state(
        db,
        monitored.id,
        is_paused=True,
    )

    db.commit()
    db.refresh(monitored)

    if competitors_updated:
        logger.info(
            "competitors_paused",
            monitored_id=str(monitored.id),
            count=competitors_updated,
        )

    logger.info(
        "monitored_pause_state_updated",
        monitored_id=str(monitored.id),
        paused_at=monitored.paused_at.isoformat() if monitored.paused_at else None,
        user_id=str(user.id),
        already_paused=was_paused,
    )

    return monitored

def resume_monitored(db: Session, monitored_id: UUID, user: User) -> MonitoredProduct:
    """ Retoma monitorado, recalcula janela e reativa concorrentes """
    monitored = _ensure_monitored_access(db, monitored_id, user)
    reference = datetime.now(timezone.utc)
    was_paused = bool(monitored.paused)
    monitored.paused = False
    monitored.paused_at = None
    resumed_schedule = compute_next_check_at(
        monitored,
        reference_time=reference,
        event_type=EVENT_RESUMED,
    )
    monitored.stability_score = resumed_schedule.stability_score
    monitored.next_check_at = resumed_schedule.next_check_at

    competitors_updated = crud_competitor.update_competitors_pause_state(
        db,
        monitored.id,
        is_paused=False,
    )

    db.commit()
    db.refresh(monitored)

    logger.info(
        "monitored_resume_state_updated",
        monitored_id=str(monitored.id),
        next_check_at=monitored.next_check_at.isoformat() if monitored.next_check_at else None,
        user_id=str(user.id),
        was_paused=was_paused,
    )

    if competitors_updated:
        logger.info(
            "competitors_resumed",
            monitored_id=str(monitored.id),
            count=competitors_updated,
        )

    # O enfileiramento na fila de prioridade Redis é responsabilidade da camada
    # de serviço (services_monitored_lifecycle). O CRUD apenas persiste o estado.
    return monitored

def delete_monitored(db: Session, monitored_id: UUID, user: User) -> list[UUID]:
    """ Remove monitorado na sessão recebida e retorna IDs para limpeza externa
    
    A gestão transacional e de lock fica na camada de serviço para manter o
    CRUD focado em persistência.
    """
    monitored = _ensure_monitored_access(db, monitored_id, user)
    db.delete(monitored)
    db.commit()
    return [monitored_id]

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
    # Falhas não representam dados novos — registre apenas a checagem.
    product.last_checked = touched_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(product)
    return product

def activate_pending_monitored(
    db: Session,
    monitored_id: UUID | None,
    *,
    commit: bool = True,
) -> MonitoredProduct | None:
    """ Transiciona monitorado de ``pending`` para ``active`` após primeira coleta bem-sucedida.

    Idempotente: se o produto já estiver ``active`` (ou em qualquer outro status),
    retorna o objeto sem modificações. Retorna ``None`` se o produto não existir.

    Args:
        db: Sessão ativa do banco de dados.
        monitored_id: UUID do produto monitorado. ``None`` é aceito para
            compatibilidade com callers que não conhecem o ID — retorna ``None``.
        commit: Quando ``True`` (padrão) commita a transação aqui.
            Passe ``False`` para integrar em uma transação externa (usa ``flush``).
    """
    if monitored_id is None:
        return None
    product = get_monitored_product_by_id(db, monitored_id)
    if product is None:
        return None
    if product.status != MonitoredStatus.pending:
        return product
    product.status = MonitoredStatus.active
    if commit:
        db.commit()
        db.refresh(product)
    else:
        db.flush()
    logger.info(
        "monitored_status_activated",
        monitored_id=str(monitored_id),
    )
    return product
