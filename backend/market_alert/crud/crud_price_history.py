""" Funções CRUD auxiliares para gravação do histórico de preços.

Os helpers evitam duplicidade de registros quando o preço permanece estável
entre coletas próximas, reduzindo ruído em comparações e relatórios. 
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from market_alert.models.models_price_history import PriceHistory
from shared.metrics.metrics_products import PRICE_HISTORY_CREATED_TOTAL
import structlog


logger = structlog.get_logger("crud_price_history")

def _normalize_checked_at(checked_at: datetime) -> datetime:
    """ Garante que o timestamp do histórico esteja em UTC e com tzinfo """
    if checked_at.tzinfo is None:
        return checked_at.replace(tzinfo=timezone.utc)
    return checked_at.astimezone(timezone.utc)

def _last_entry_for_product(
    db: Session,
    *,
    monitored_product_id: UUID | None = None,
    competitor_product_id: UUID | None = None,
) -> PriceHistory | None:
    """ Retorna o último histórico registrado para o produto informado """
    query = db.query(PriceHistory)
    if monitored_product_id is not None:
        query = query.filter(PriceHistory.monitored_product_id == monitored_product_id)
    if competitor_product_id is not None:
        query = query.filter(PriceHistory.competitor_product_id == competitor_product_id)
    return query.order_by(PriceHistory.checked_at.desc()).first()

def _is_duplicate_price(entry: PriceHistory | None, price: Decimal, *, currency: str | None) -> bool:
    """ Verifica se o último registro já contém o mesmo preço/currency

    Essa checagem evita gerar linhas repetidas durante rechecagens sem alteração
    de preço, mesmo que o ``checked_at`` seja diferente.
    """
    if entry is None:
        return False
    return entry.price == price and (currency is None or entry.currency == currency)

def create_for_monitored(
    db: Session,
    monitored_product_id: UUID,
    price: Decimal,
    currency: str | None,
    checked_at: datetime,
    *,
    commit: bool = False,
) -> PriceHistory:
    """ Registra histórico para monitorados sem abrir transações extras.

    Mantemos a idempotência para preços estáveis e, por padrão, apenas
    ``flush`` das alterações para permitir controle transacional pelo caller.
    Quando ``commit`` é ``True`` a confirmação é realizada aqui.
    """
    normalized_checked_at = _normalize_checked_at(checked_at)

    existing = _last_entry_for_product(db, monitored_product_id=monitored_product_id)
    if existing and _is_duplicate_price(existing, price, currency=currency):
        return existing

    entry = PriceHistory(
        monitored_product_id=monitored_product_id,
        price=price,
        currency=currency,
        checked_at=normalized_checked_at,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()

    PRICE_HISTORY_CREATED_TOTAL.labels(owner="monitored").inc()
    logger.info(
        "price_history_created",
        owner_type="monitored",
        monitored_product_id=str(monitored_product_id),
        price=str(price),
        currency=currency,
        checked_at=normalized_checked_at.isoformat(),
    )
    return entry

def create_for_competitor(
    db: Session,
    competitor_product_id: UUID,
    price: Decimal,
    currency: str | None,
    checked_at: datetime,
    *,
    commit: bool = False,
) -> PriceHistory:
    """ Registra histórico para concorrentes em sincronia com o caller.

    O comportamento de idempotência é mantido; a confirmação da transação fica
    a critério de quem chamou para que produto e histórico sejam persistidos
    juntos quando necessário.
    """
    normalized_checked_at = _normalize_checked_at(checked_at)

    existing = _last_entry_for_product(db, competitor_product_id=competitor_product_id)
    if existing and _is_duplicate_price(existing, price, currency=currency):
        return existing

    entry = PriceHistory(
        competitor_product_id=competitor_product_id,
        price=price,
        currency=currency,
        checked_at=normalized_checked_at,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()

    PRICE_HISTORY_CREATED_TOTAL.labels(owner="competitor").inc()
    logger.info(
        "price_history_created",
        owner_type="competitor",
        competitor_product_id=str(competitor_product_id),
        price=str(price),
        currency=currency,
        checked_at=normalized_checked_at.isoformat(),
    )
    return entry
