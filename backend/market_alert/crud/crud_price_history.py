""" Funções CRUD auxiliares para gravação do histórico de preços """

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from market_alert.models.models_price_history import PriceHistory


def create_for_monitored(
    db: Session,
    monitored_product_id: UUID,
    price: Decimal,
    currency: str | None,
    checked_at: datetime,
) -> PriceHistory:
    """ Registra histórico para produto monitorado mantendo carimbo de coleta """
    existing = (
        db.query(PriceHistory)
        .filter(
            PriceHistory.monitored_product_id == monitored_product_id,
            PriceHistory.price == price,
            PriceHistory.checked_at == checked_at,
        )
        .first()
    )
    if existing:
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
    """ Registra histórico para concorrente permitindo restrear variações """
    existing = (
        db.query(PriceHistory)
        .filter(
            PriceHistory.competitor_product_id == competitor_product_id,
            PriceHistory.price == price,
            PriceHistory.checked_at == checked_at,
        )
        .first()
    )
    if existing:
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
