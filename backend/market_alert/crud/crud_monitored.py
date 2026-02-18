""" Operações CRUD para produtos monitorados pelo sistema """

from typing import List, Optional, Tuple

from uuid import UUID
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urlparse

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased
import structlog

from backend.shared.schemas.shared_schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo
from shared.utils import sanitize_text
from shared.utils.url_validation import normalize_product_url_for_storage
from shared.utils.redis_locks import acquire_product_lock, release_product_lock
from shared.infra.db import SessionLocal

from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.models.models_comparisons import PriceComparisonSummary
from market_alert.models.models_price_history import PriceHistory
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.crud import crud_competitor, crud_price_history
from market_alert.core.config_alert import settings
from market_alert.models import User
from market_alert.services.services_priority_queue import PriorityQueueService
from market_alert.services.services_priority_queue_manager import (
    enqueue_monitored_now,
    remove_from_priority_queue,
)
from market_alert.utils.interval_calculator_products import calculate_next_check_at, calculate_stability_score, STABILITY_UNSTABLE
from market_alert.utils.price_utils import normalize_scraped_price, should_create_price_history


logger = structlog.get_logger("crud_monitored")
_LOCK_TTL_SECONDS = min(settings.PRODUCT_LOCK_TTL_SECONDS, 30)

def _ensure_monitored_access(db: Session, monitored_id: UUID, user: User) -> MonitoredProduct:
    """ Obtém monitorado garantindo posse do usuário """
    product = get_monitored_product_by_id(db, monitored_id)
    if product is None:
        raise MonitoredNotFoundError("Monitorado não encontrado")
    if product.user_id != user.id:
        raise MonitoredOwnershipError("Usuário sem permissão para este monitorado")
    return product

def _acquire_monitored_lock(monitored_id: UUID) -> str:
    """ Adquire lock curto para operações críticas do monitorado """
    acquired, owner = acquire_product_lock(monitored_id, ttl_seconds=_LOCK_TTL_SECONDS)
    if not acquired:
        raise MonitoredLockError("Não foi possível adquirir lock do monitorado")
    return owner or ""

class MonitoredOwnershipError(PermissionError):
    """Erro lançado quando o usuário não possui acesso ao monitorado"""

class MonitoredNotFoundError(LookupError):
    """Erro lançado quando o monitorado não é localizado"""

class MonitoredLockError(RuntimeError):
    """Erro lançado quando o lock exclusivo não pode ser adquirido"""

def _to_decimal(value: Decimal | float | int | str | None) -> Decimal | None:
    """ Converte valores diversos para `Decimal` preservando `None`
    
    A normalização evita comparações inconsistentes quando preço chega como
    string ou float após coleta do scraper
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    
def _different_price(previous_price: Decimal | float | int | str | None, current_price: Decimal | float | int | str | None) -> bool:
    """ Compara preços convertendo para `Decimal` para evitar falsos negativos """
    previous = _to_decimal(previous_price)
    current = _to_decimal(current_price)
    return previous != current

def _update_price_change_tracking(
    monitored: MonitoredProduct,
    new_price: Decimal | None,
    old_price: Decimal | None,
    collected_at: datetime,
) -> None:
    """ Atualiza rastreio de mudança de preço e marca coleta em grupo """
    collected_reference = collected_at.astimezone(timezone.utc) if collected_at.tzinfo else collected_at.replace(tzinfo=timezone.utc)
    monitored.group_collected_at = collected_reference

    if _different_price(old_price, new_price):
        #Resetamos estabilidade para acelerar rechecagem após mudança de preço
        monitored.last_price_change_at = collected_reference
        monitored.stability_score = STABILITY_UNSTABLE
        logger.info(
            "monitored_price_change_detected",
            monitored_id=str(monitored.id),
            old_price=str(old_price) if old_price is not None else None,
            new_price=str(new_price) if new_price is not None else None,
            collected_at=collected_reference.isoformat(),
        )

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
    
    effective_name, _ = _prepare_effective_name(
        name_identification,
        scraped_name=None,
        product_url=normalized_url,
    )

    reference_time = datetime.now(timezone.utc)
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

    #Calcula o próximo agendamento após istanciar o objeto para reutilizar referências e evitar uso de variáveis inexistentes
    pending.next_check_at = calculate_next_check_at(pending, collected_at=reference_time)
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
    """ Cria ou atualiza um produto monitorado a partir de dados de scraping """
    normalized_url = normalize_product_url_for_storage(product_data.product_url)
    #A URL chega validada pela API e é preservada para manter unicidade baseada na entrada do usuário

    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)
    else:
        last_checked = last_checked.astimezone(timezone.utc)

    #Verifica se o produto já existe para o usuário
    existing = get_monitored_product_by_user_and_url(db, user_id, normalized_url)

    resolved_name, fallback_name = _prepare_effective_name(
        product_data.name_identification,
        scraped_name,
        normalized_url,
    )

    if existing:
        resolved_price = normalize_scraped_price(scraped_info.current_price)
        availability = _resolve_availability(scraped_info.availability, scraped_info.last_status)
        last_status = scraped_info.last_status or existing.last_status
        inactive_due_to_data = availability is False or resolved_price is None

        #Atualiza somente campos relevantes
        if product_data.name_identification and existing.name_identification != product_data.name_identification:
            existing.name_identification = product_data.name_identification
        elif _should_replace_with_scraped(existing.name_identification, fallback_name, scraped_name):
            #Substituímos o placeholder por nome real vindo do scraping
            existing.name_identification = sanitize_text(scraped_name) or fallback_name
        elif existing.name_identification is None:
            existing.name_identification = resolved_name
        previous_price = existing.current_price
        previous_status = existing.status
        price_changed = _different_price(previous_price, resolved_price)
        resolved_currency = currency or scraped_info.currency or existing.currency

        #Executa commit único garantindo atomicidade com o histórico
        logger.info(
            "monitored_commit_preview",
            product_id=str(existing.id),
            availability=availability,
            last_status=last_status,
            resolved_price=str(resolved_price) if resolved_price is not None else None,
            price_changed=price_changed,
        )
        collected_reference = collected_at or last_checked

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

            #Persistimos histórico antes do refresh para alinhar commit único à alteração de preço
            if price_history_needed:
                crud_price_history.create_for_monitored(
                    db,
                    existing.id,
                    resolved_price,
                    resolved_currency,
                    last_checked,
                )

            _update_price_change_tracking(
                existing,
                new_price=resolved_price,
                old_price=previous_price,
                collected_at=collected_reference,
            )
            #A estabilidade precisa ser recalculada antes do agendamento para refletir mudanças de preço no mesmo ciclo
            existing.stability_score = calculate_stability_score(
                existing,
                reference_time=last_checked,
            )
            existing.next_check_at = calculate_next_check_at(existing, collected_at=last_checked)

            db.commit()
        except Exception:
            #Rollback evita manter sessão suja em falhas de gravação e previne transações aninhadas
            db.rollback()
            raise

        db.refresh(existing)
        existing._price_changed = price_changed
        existing._availability_changed = previous_status != existing.status
        
        logger.info(
            "updated_monitored",
            product_id=str(existing.id),
            price_changed=existing._price_changed,
            availability_changed=existing._availability_changed,
            last_checked=last_checked.isoformat(),
            availability=existing.availability,
            last_status=existing.last_status,
        )
        return existing

    #Se não existir, cria o registro
    resolved_price = normalize_scraped_price(scraped_info.current_price)
    resolved_currency = currency or scraped_info.currency
    availability = _resolve_availability(scraped_info.availability, scraped_info.last_status)
    last_status = scraped_info.last_status
    inactive_due_to_data = availability is False or resolved_price is None

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
        last_checked=last_checked,
        last_scraped_at=last_checked,
        collected_at=collected_at or last_checked,
        next_check_at=None,
        currency=resolved_currency,
        etag=etag,
        last_modified=last_modified,
        availability=availability,
        last_status=last_status,
    )
    _update_price_change_tracking(
        new,
        new_price=resolved_price,
        old_price=None,
        collected_at=collected_at or last_checked,
    )
    new.stability_score = calculate_stability_score(
        new,
        reference_time=last_checked,
    )
    new.next_check_at = calculate_next_check_at(new, collected_at=last_checked)
    
    try:
        db.add(new)
        db.flush()
        history_allowed = should_create_price_history(resolved_price, availability)
        if not history_allowed:
            logger.info(
                "product_marked_unavailable",
                product_id=str(new.id),
                availability=availability,
                last_status=last_status,
                availability_inferred=availability is None,
                price_missing=resolved_price is None,
            )
        if resolved_price is not None and history_allowed:
            crud_price_history.create_for_monitored(
                db,
                new.id,
                resolved_price,
                resolved_currency,
                last_checked,
            )
        db.commit()
    except Exception:
        #Rollback mantém atomicidade entre produto e histórico quando ocorrer falha
        db.rollback()
        raise

    db.refresh(new)

    new._price_changed = True
    new._availability_changed = True
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

    try:
        remove_from_priority_queue(monitored.id, source="user_paused")
    except Exception as exc:
        #Evita bloquear a pausa quando Redis estiver indisponível
        logger.warning(
            "monitored_priority_queue_remove_failed",
            monitored_id=str(monitored.id),
            error=str(exc),
        )

    return monitored

def resume_monitored(db: Session, monitored_id: UUID, user: User) -> MonitoredProduct:
    """ Retoma monitorado, recalcula janela e reativa concorrentes """
    monitored = _ensure_monitored_access(db, monitored_id, user)
    reference = datetime.now(timezone.utc)
    was_paused = bool(monitored.paused)
    monitored.paused = False
    monitored.paused_at = None
    monitored.next_check_at = calculate_next_check_at(monitored, collected_at=reference)

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
    
    try:
        enqueue_monitored_now(monitored.id, source="user_resumed")
    except Exception as exc:
        #Mantém a retomada mesmo que o Redis não responda
        logger.warning(
            "monitored_resume_queue_enqueue_failed",
            monitored_id=str(monitored.id),
            error=str(exc),
        )

    return monitored

def delete_monitored(db: Session, monitored_id: UUID, user: User) -> None:
    """ Remove monitorado utilizando sessão dedicada para isolar a transação """
    lock_owner: str | None = None
    dedicated_session: Session | None = None
    try:
        #Utiliza nova sessão para evitar interferência de transações externas do ciclo da requisição
        dedicated_session = SessionLocal()
        monitored = _ensure_monitored_access(dedicated_session, monitored_id, user)
        lock_owner = _acquire_monitored_lock(monitored_id)
        queue_service = PriorityQueueService()
        removed = queue_service.remove(str(monitored_id))
        if removed:
            logger.info(
                "monitored_removed_from_priority_queue",
                monitored_id=str(monitored_id),
                reason="monitored_deleted",
            )
        else:
            #Garante a deleção mesmo que o redis esteja indisponível
            logger.warning(
                "monitored_priority_queue_remove_failed",
                monitored_id=str(monitored_id),
                reason="monitored_deleted",
            )

        dedicated_session.delete(monitored)
        dedicated_session.commit()

    finally:
        if dedicated_session:
            dedicated_session.close()
        if lock_owner:
            release_product_lock(monitored_id, lock_owner)

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
