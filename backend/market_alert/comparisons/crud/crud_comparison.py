""" Operações de persistência para resultados de comparação de preços """

from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from market_alert.models.models_comparisons import PriceComparison, PriceComparisonSummary


def create_price_comparison(
    db: Session,
    monitored_product_id: UUID,
    data: dict,
    *,
    status: Optional[str] = None,
    is_complete: bool = False,
    included_competitors_count: Optional[int] = None,
    competitors_with_price_count: Optional[int] = None,
    completed_at: Optional[datetime] = None,
) -> PriceComparison:
    """ Persiste o resultado de uma comparação para o produto monitorado """
    comparison = PriceComparison(
        monitored_product_id=monitored_product_id,
        data=data,
        status=status,
        is_complete=is_complete,
        included_competitors_count=included_competitors_count,
        competitors_with_price_count=competitors_with_price_count,
        completed_at=completed_at,
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    return comparison

def create_price_comparison_summary(
    db: Session,
    monitored_product_id: UUID,
    comparison_id: UUID,
    aggregates: Dict[str, object],
) -> PriceComparisonSummary:
    """ Armazena o resumo agregado associado a uma comparação """
    summary = PriceComparisonSummary(
        monitored_product_id=monitored_product_id,
        comparison_id=comparison_id,
        aggregates=aggregates,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary

def upsert_price_comparison_summary(
    db: Session,
    monitored_product_id: UUID,
    comparison_id: UUID,
    aggregates: Dict[str, object],
) -> PriceComparisonSummary:
    """ Cria ou atualiza o resumo agregado associado a uma comparação """

    summary = (
        db.query(PriceComparisonSummary)
        .filter(PriceComparisonSummary.comparison_id == comparison_id)
        .first()
    )

    if summary is None:
        return create_price_comparison_summary(
            db,
            monitored_product_id,
            comparison_id,
            aggregates,
        )

    summary.aggregates = aggregates
    summary.timestamp = datetime.now(timezone.utc)
    summary.monitored_product_id = monitored_product_id
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary

def get_latest_comparisons(db: Session, monitored_product_id: UUID, limit: int = 10) -> List[PriceComparison]:
    """ Recupera os registros de comparação mais recentes para um produto """
    return (
        db.query(PriceComparison)
        .filter(PriceComparison.monitored_product_id == monitored_product_id)
        .order_by(PriceComparison.timestamp.desc())
        .limit(limit)
        .all()
    )

def paginate_comparisons(
    db: Session,
    monitored_product_id: UUID,
    *,
    page: int,
    per_page: int,
) -> Tuple[int, List[PriceComparison]]:
    """ Recupera comparações de forma paginada para um produto monitorado """
    base_query = db.query(PriceComparison).filter(
        PriceComparison.monitored_product_id == monitored_product_id
    )
    total = base_query.count()
    comparisons = (
        base_query.order_by(PriceComparison.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return total, comparisons

def get_latest_comparison(db: Session, monitored_product_id: UUID) -> Optional[PriceComparison]:
    """ Retorna a comparação mais recente para o produto monitorado """
    return (
        db.query(PriceComparison)
        .filter(PriceComparison.monitored_product_id == monitored_product_id)
        .order_by(PriceComparison.timestamp.desc())
        .first()
    )

def get_comparison_by_id(db: Session, comparison_id: UUID) -> Optional[PriceComparison]:
    """ Obtém um registro de comparação específico pelo ID """
    return db.query(PriceComparison).filter(PriceComparison.id == comparison_id).first()

def get_latest_summary(db: Session, monitored_product_id: UUID) -> Optional[PriceComparisonSummary]:
    """ Retorna o resumo mais recente disponível para o produto monitorado """
    return (
        db.query(PriceComparisonSummary)
        .filter(PriceComparisonSummary.monitored_product_id == monitored_product_id)
        .order_by(PriceComparisonSummary.timestamp.desc())
        .first()
    )

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

def get_latest_summaries_for_products(
    db: Session,
    product_ids: list[UUID],
) -> dict[UUID, PriceComparisonSummary]:
    """ Retorna o resumo mais recente registrado para cada produto informado """
    if not product_ids:
        return {}

    latest_subquery = (
        db.query(
            PriceComparisonSummary.monitored_product_id.label("monitored_product_id"),
            func.max(PriceComparisonSummary.timestamp).label("max_timestamp"),
        )
        .filter(PriceComparisonSummary.monitored_product_id.in_(product_ids))
        .group_by(PriceComparisonSummary.monitored_product_id)
        .subquery()
    )

    latest_rows = (
        db.query(PriceComparisonSummary)
        .join(
            latest_subquery,
            (
                PriceComparisonSummary.monitored_product_id
                == latest_subquery.c.monitored_product_id
            )
            & (PriceComparisonSummary.timestamp == latest_subquery.c.max_timestamp)
        )
        .all()
    )
    return {row.monitored_product_id: row for row in latest_rows}
