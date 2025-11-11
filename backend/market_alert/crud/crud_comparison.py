""" Operações de persistência para resultados de comparação de preços """

from typing import Optional, List
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from market_alert.models.models_comparisons import PriceComparison


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

def get_latest_comparisons_for_products(db: Session, product_ids: list[UUID]) -> dict[UUID, PriceComparison]:
    """ Retorna a última comparação registrada para cada produto informado """
    if not product_ids:
        return {}
    
    #Seleciona o timestamp mais recente por produto para evitar duplicidade de registros
    latest_subquery = (
        db.query(
            PriceComparison.monitored_product_id.label("monitored_product_id"),
            func.max(PriceComparison.timestamp).label("max_timestamp")
        )
        .filter(PriceComparison.monitored_product_id.in_(product_ids))
        .group_by(PriceComparison.monitored_product_id)
        .subquery()
    )

    latest_rows = (
        db.query(PriceComparison)
        .join(
            latest_subquery,
            (
                PriceComparison.monitored_product_id == latest_subquery.c.monitored_product_id
            )
            & (PriceComparison.timestamp == latest_subquery.c.max_timestamp)
        )
        .all()
    )
    return {row.monitored_product_id: row for row in latest_rows}
