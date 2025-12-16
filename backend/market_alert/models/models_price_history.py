"""Models relacionados ao histórico de preços.

Este módulo define o modelo `PriceHistory`, que representa leituras de preço
coletadas ao longo do tempo para um produto monitorado (`MonitoredProduct`) ou
um produto concorrente (`CompetitorProduct`). Cada registro corresponde a uma
medição (ou "ponto") com carimbo de tempo (`checked_at`) e moeda.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from shared.infra.db import Base


class PriceHistory(Base):
    """ Entrada de histórico de preço """

    __tablename__ = "price_history"

    #ID único com UUIDv4
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    #Referência ao dono do histórico. Apenas um dos dois deve ser preenchido.
    monitored_product_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    competitor_product_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("competitor_products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    #Informação monetária
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(8), nullable=True)

    #Controle de data: `checked_at` deve refletir o momento da coleta, `created_at` indica quando o registro foi persistido.
    checked_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "(monitored_product_id IS NOT NULL) OR (competitor_product_id IS NOT NULL)",
            name="price_history_owner_check",
        ),
    )

    #Relacionamentos para permitir consultas do dono -> histórico e vice-versa.
    monitored_product = relationship("MonitoredProduct", back_populates="price_history")
    competitor_product = relationship("CompetitorProduct", back_populates="price_history")

    def __repr__(self) -> str:
        """ Representação útil para debugging e logs. Mostra o dono (UUID), preço, moeda e carimbo de coleta """
        owner = self.monitored_product_id or self.competitor_product_id
        return (
            f"<PriceHistory(owner={owner} price={self.price} "
            f"currency={self.currency} checked_at={self.checked_at})>"
        )
    