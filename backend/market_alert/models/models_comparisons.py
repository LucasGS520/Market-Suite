""" Modelos de dados referentes às comparações de preços """

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    ForeignKey,
    DateTime,
    Integer,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from shared.infra.db import Base


class PriceComparison(Base):
    """ Registro das comparações de preços realizadas """

    __tablename__ = "price_comparisons"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitored_product_id = Column(PG_UUID(as_uuid=True), ForeignKey("monitored_products.id", ondelete="CASCADE"), nullable=False, index=True)

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    data = Column(JSON, nullable=False)

    # Metadados de auditoria — preenchidos pelo worker ao finalizar a comparação
    competitors_with_price_count = Column(Integer, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PriceComparison id={self.id} monitored_product_id={self.monitored_product_id}>"
        )

class PriceComparisonSummary(Base):
    """Resumo agregado de uma comparação de preços """

    __tablename__ = "price_comparison_summaries"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitored_product_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    comparison_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("price_comparisons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    aggregates = Column(JSON, nullable=False)

    def __repr__(self) -> str:
        return (
            "<PriceComparisonSummary "
            f"id={self.id} monitored_product_id={self.monitored_product_id} "
            f"comparison_id={self.comparison_id}>"
        )
    