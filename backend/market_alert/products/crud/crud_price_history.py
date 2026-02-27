""" Funções CRUD auxiliares para gravação do histórico de preços.

Os helpers evitam duplicidade de registros quando o preço permanece estável
entre coletas próximas, reduzindo ruído em comparações e relatórios. 
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from market_alert.models.models_price_history import PriceHistory
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

def get_latest_price_for_competitor(
    db: Session,
    competitor_id: UUID,
) -> Optional[Decimal]:
    """ Retorna o preço mais recente registrado no histórico para um concorrente.

    Usado como fallback quando ``competitor.current_price`` está ausente,
    permitindo que a comparação use o último preço coletado mesmo que o
    scraping mais recente não tenha persistido um preço novo.

    Ordena por ``checked_at`` e ``created_at`` (secundário) para garantir
    o registro mais recente mesmo quando dois registros têm o mesmo timestamp.

    Args:
        db: Sessão ativa do banco de dados.
        competitor_id: UUID do produto concorrente.

    Returns:
        Decimal com o preço mais recente, ou None se não houver histórico.
    """
    return (
        db.query(PriceHistory.price)
        .filter(PriceHistory.competitor_product_id == competitor_id)
        .order_by(desc(PriceHistory.checked_at), desc(PriceHistory.created_at))
        .limit(1)
        .scalar()
    )

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

    logger.info(
        "price_history_created",
        owner_type="monitored",
        monitored_product_id=str(monitored_product_id),
        price=str(price),
        currency=currency,
        checked_at=normalized_checked_at.isoformat(),
    )
    return entry

def fetch_recent_prices(
    db: Session,
    monitored_id: UUID,
    limit: int = 2,
) -> tuple[float | None, float | None]:
    """ Retorna o penúltimo e o último preço registrado para um monitorado.

    Usado para compor snapshots de notificação sem expor query direta nas tasks.

    Returns:
        Tupla ``(price_previous, price_current)``. Ambos ``None`` se não houver
        histórico suficiente.
    """
    history = (
        db.query(PriceHistory)
        .filter(PriceHistory.monitored_product_id == monitored_id)
        .order_by(PriceHistory.checked_at.desc())
        .limit(limit)
        .all()
    )
    if not history:
        return None, None
    current = float(history[0].price) if history[0].price is not None else None
    previous: float | None = None
    if len(history) > 1 and history[1].price is not None:
        previous = float(history[1].price)
    return previous, current


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

    logger.info(
        "price_history_created",
        owner_type="competitor",
        competitor_product_id=str(competitor_product_id),
        price=str(price),
        currency=currency,
        checked_at=normalized_checked_at.isoformat(),
    )
    return entry
