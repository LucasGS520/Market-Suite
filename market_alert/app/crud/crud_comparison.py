""" Operações de persistência para resultados de comparação de preços """

from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models_comparisons import PriceComparison


def create_price_comparison(db: Session, monitored_product_id: UUID, data: dict) -> PriceComparison:
    """ Persiste o resultado de uma comparação para o produto monitorado """
    comparison = PriceComparison(
        monitored_product_id=monitored_product_id,
        data=data
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    return comparison

def get_latest_comparisons(db: Session, monitored_product_id: UUID, limit: int = 10) -> List[PriceComparison]:
    """ Recupera os registros de comparação mais recentes para um produto """
    return (
        db.query(PriceComparison)
        .filter(PriceComparison.monitored_product_id == monitored_product_id)
        .order_by(PriceComparison.timestamp.desc())
        .limit(limit)
        .all()
    )

def get_comparison_by_id(db: Session, comparison_id: UUID) -> Optional[PriceComparison]:
    """ Obtém um registro de comparação específico pelo ID """
    return db.query(PriceComparison).filter(PriceComparison.id == comparison_id).first()
