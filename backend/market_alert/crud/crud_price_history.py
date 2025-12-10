""" Funções CRUD auxiliares para gravação do histórico de preços.

Os helpers evitam duplicidade de registros quando o preço permanece estável
entre coletas próximas, reduzindo ruído em comparações e relatórios. 
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from market_alert.models.models_price_history import PriceHistory


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
) -> PriceHistory:
    """ Registra histórico para produto monitorado mantendo carimbo de coleta

    A função é idempotente para preços repetidos próximos, retornando o último
    registro quando não há alteração para evitar ruído no histórico.
    """
    existing = _last_entry_for_product(db, monitored_product_id=monitored_product_id)
    if existing and _is_duplicate_price(existing, price, currency=currency):
        return existing

    entry = PriceHistory(
        monitored_product_id=monitored_product_id,
        price=price,
        currency=currency,
        checked_at=checked_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

def create_for_competitor(
    db: Session,
    competitor_product_id: UUID,
    price: Decimal,
    currency: str | None,
    checked_at: datetime,
) -> PriceHistory:
    """ Registra histórico para concorrente permitindo rastrear variações.

    Assim como nos monitorados, evita duplicação quando não há mudança de preço
    entre coletas próximas.
    """
    existing = _last_entry_for_product(db, competitor_product_id=competitor_product_id)
    if existing and _is_duplicate_price(existing, price, currency=currency):
        return existing

    entry = PriceHistory(
        competitor_product_id=competitor_product_id,
        price=price,
        currency=currency,
        checked_at=checked_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
