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

from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.models.models_comparisons import PriceComparisonSummary
from market_alert.models.models_price_history import PriceHistory
from market_alert.models.models_alerts import AlertRule, NotificationLog
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.enums.enums_alerts import AlertType
from market_alert.schemas.schemas_alert_rules import AlertRuleCreate
from market_alert.crud import crud_alert_rules
from market_alert.crud import crud_price_history
from market_alert.core.config_alert import settings


logger = structlog.get_logger("crud_monitored")

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

def _compute_next_check_at(monitored: MonitoredProduct, reference: datetime | None = None) -> datetime:
    """ Calcula o próximo agendamento respeitando configuração dinâmica do item.

    A função usa o atributo opcional ``check_interval`` quando presente e,
    caso o valor seja inválido ou ausente, aplica ``RECHECK_INTERVAL_DEFAULT``
    como fallback. O cálculo sempre considera timezone UTC para garantir
    previsibilidade entre workers e Beat.
    """
    base_time = reference or datetime.now(timezone.utc)
    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)
    interval_seconds = getattr(monitored, "check_interval", None)
    if not isinstance(interval_seconds, int) or interval_seconds <= 0:
        interval_seconds = settings.RECHECK_INTERVAL_DEFAULT
    return base_time + timedelta(seconds=interval_seconds)

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

def count_notifications_for_monitored_product(
    db: Session,
    user_id: UUID,
    monitored_product_id: UUID
) -> int:
    """Conta notificações enviadas para regras vinculadas ao monitorado."""
    result = (
        db.query(func.count(NotificationLog.id))
        .join(AlertRule, NotificationLog.alert_rule_id == AlertRule.id)
        .filter(
            NotificationLog.user_id == user_id,
            AlertRule.monitored_product_id == monitored_product_id,
        )
        .scalar()
    )
    return int(result or 0)

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
    pending.next_check_at = _compute_next_check_at(pending, reference=reference_time)
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
        resolved_price = _to_decimal(scraped_info.current_price)
        availability = scraped_info.availability
        last_status = scraped_info.last_status or existing.last_status

        if availability is False:
            resolved_price = None

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
            existing.next_check_at = _compute_next_check_at(existing, reference=last_checked)
            existing.status = MonitoredStatus.inactive if availability is False else MonitoredStatus.active
            existing.availability = availability
            existing.last_status = last_status
            existing.normalized_url = normalized_url

            price_history_needed = price_changed and resolved_price is not None and availability is not False

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
    resolved_price = _to_decimal(scraped_info.current_price)
    resolved_currency = currency or scraped_info.currency
    availability = scraped_info.availability
    last_status = scraped_info.last_status

    if availability is False:
        resolved_price = None

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
        status=MonitoredStatus.inactive if availability is False else MonitoredStatus.active,
        last_checked=last_checked,
        last_scraped_at=last_checked,
        next_check_at=None,
        currency=resolved_currency,
        etag=etag,
        last_modified=last_modified,
        availability=availability,
        last_status=last_status,
    )
    new.next_check_at = _compute_next_check_at(new, reference=last_checked)
    
    try:
        db.add(new)
        db.flush()
        if resolved_price is not None and availability is not False:
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
        MonitoredProduct.current_price.isnot(None),
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

    #Conta alertas ativos associados ao produto para priorizar itens mais sensíveis
    alert_rows = (
        db.query(
            AlertRule.monitored_product_id,
            func.count(AlertRule.id).label("alerts_count"),
        )
        .filter(
            AlertRule.monitored_product_id.in_(candidate_ids),
            AlertRule.enabled.is_(True),
        )
        .group_by(AlertRule.monitored_product_id)
        .all()
    )
    alert_map = {row.monitored_product_id: int(row.alerts_count) for row in alert_rows}

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
            alert_map.get(product.id, 0),
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
    # Falhas não representam dados novos — registre apenas a checagem.
    product.last_checked = touched_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(product)
    return product
