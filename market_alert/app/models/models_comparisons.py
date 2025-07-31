""" Modelos de dados referentes às comparações de preços """

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from infra.db import Base


class PriceComparison(Base):
    """ Registro das comparações de preços realizadas """

    __tablename__ = "price_comparisons"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitored_product_id = Column(PG_UUID(as_uuid=True), ForeignKey("monitored_products.id", ondelete="CASCADE"), nullable=False, index=True)

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    data = Column(JSON, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<PriceComparison id={self.id} monitored_product_id={self.monitored_product_id}>"
        )
