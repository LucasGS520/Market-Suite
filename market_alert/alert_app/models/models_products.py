""" Modelos SQLAlchemy para produtos monitorados e concorrentes """

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, ForeignKey, DateTime, Text, Boolean, Float, Enum as PgEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from infra.db import Base
from app.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus


# ---------- PRODUTO MONITORADO ----------
class MonitoredProduct(Base):
    """ Produto que será acompanhado pelo usuário """

    __tablename__ = "monitored_products" #Define o nome da tabela como monitored_products

    __table_args__ = (
        UniqueConstraint("user_id", "product_url", name="uq_user_product_url"),
    )

    #ID unico com UUIDv4
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    #Informações basicas do produto
    name_identification = Column("name", String, nullable=False)
    monitoring_type = Column(PgEnum(MonitoringType, name="monitoring_type_enum"), nullable=False)

    #Para produtos via API (search_query) e scraping (product_url)
    search_query = Column(String, nullable=True, index=True)
    product_url = Column(Text, nullable=False)

    target_price = Column(Numeric(10,2), nullable=True)
    current_price = Column(Numeric(10,2), nullable=True)
    free_shipping = Column(Boolean, default=False)
    thumbnail = Column(Text, nullable=True)

    #Cache condicional
    etag = Column(String, nullable=True)
    last_modified = Column(DateTime(timezone=True), nullable=True)

    #Controle de status
    status = Column(PgEnum(MonitoredStatus, name="monitored_status_enum"), nullable=False, default=MonitoredStatus.active)
    last_checked = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    #Relacionamento com CompetitorProduct
    competitors = relationship("CompetitorProduct", back_populates="monitored_product", cascade="all, delete-orphan")
    scraping_errors = relationship("ScrapingError", back_populates="product", cascade="all, delete-orphan", lazy="dynamic")

    def __repr__(self):
        return (
            f"<MonitoredProduct("
            f"name_identification={self.name_identification},"
            f"user_id={self.user_id},"
            f"type={self.monitoring_type},"
            f"status={self.status}"
            f")>"
        )


# ---------- PRODUTO CONCORRENTE ----------
class CompetitorProduct(Base):
    """ Produto concorrente usado para comparação """

    __tablename__ = "competitor_products"

    __table_args__ = (
        UniqueConstraint("monitored_product_id", "product_url", name="uq_competitor_url"),
    )

    #ID unico com UUIDv4
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitored_product_id = Column(PG_UUID(as_uuid=True), ForeignKey("monitored_products.id"), nullable=False, index=True)

    #Dados do concorrente
    name_competitor = Column("name", String, nullable=False)
    product_url = Column(Text, nullable=False)

    current_price = Column(Numeric(10,2), nullable=False)
    old_price = Column(Numeric(10,2), nullable=True)
    free_shipping = Column(Boolean, default=False)
    seller = Column(String, nullable=True)
    seller_rating = Column(Float, nullable=True)
    thumbnail = Column(String, nullable=True)

    #Cache condicional
    etag = Column(String, nullable=True)
    last_modified = Column(DateTime(timezone=True), nullable=True)

    #Controle de status
    status = Column(PgEnum(ProductStatus, name="product_status_enum"), nullable=False, default=ProductStatus.available)
    last_checked = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    #Relacionamento com MonitoredProduct
    monitored_product = relationship("MonitoredProduct", back_populates="competitors")

    def __repr__(self):
        return (
            f"<CompetitorProduct("
            f"name_competitor={self.name_competitor},"
            f"price={self.current_price},"
            f"status={self.status}"
            f")>"
        )
