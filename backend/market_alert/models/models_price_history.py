""" Modelos responsáveis por registrar o histórico de preços coletados """

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from shared.infra.db import Base


class PriceHistory(Base):
    """ Entrada de histórico que preserva oscilações de preço e moeda """

    __tablename__ = "price_history"

    #ID unico com UUIDv4
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitored_product_id = Column(PG_UUID(as_uuid=True), ForeignKey("monitored_products.id", ondelete="CASCADE"), nullable=True, index=True)
    competitor_product_id = Column(PG_UUID(as_uuid=True), ForeignKey("competitor_products.id", ondelete="CASCADE"), nullable=True, index=True)

    #Informações de preço
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(8), nullable=True)
    
    #Controle de data e coleta
    checked_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "(monitored_product_id IS NOT NULL) OR (competitor_product_id IS NOT NULL)",
            name="price_history_owner_check",
        ),
    )

    monitored_product = relationship("MonitoredProduct", back_populates="price_history")
    competitor_product = relationship("CompetitorProduct", back_populates="price_history")

    def __repr__(self) -> str:
        """ Retorna representação amigável para depuração """
        owner = self.monitored_product_id or self.competitor_product_id
        return (
            f"<PriceHistory(owner={owner} price={self.price} "
            f"currency={self.currency} checked_at={self.checked_at})>"
        )
    