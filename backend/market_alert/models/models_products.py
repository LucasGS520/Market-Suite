""" Modelos SQLAlchemy para produtos monitorados e concorrentes.

Os relacionamentos dependem de cascata no banco para remover concorrentes
atrelados a um monitorado sem precisar de deleções manuais em código. 
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Numeric,
    ForeignKey,
    DateTime,
    Text,
    Boolean,
    Float,
    Enum as PgEnum,
    UniqueConstraint,
    Integer,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from shared.infra.db import Base
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.models.models_price_history import PriceHistory


# ---------- PRODUTO MONITORADO ----------
class MonitoredProduct(Base):
    """ Produto que será acompanhado pelo usuário """

    __tablename__ = "monitored_products" #Define o nome da tabela como monitored_products

    __table_args__ = (
        #Garante unicidade considerando URL canônica normalizada
        UniqueConstraint("user_id", "normalized_url", name="uq_user_normalized_url"),
    )

    #ID unico com UUIDv4
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    #Informações basicas do produto
    name_identification = Column("name", String, nullable=False, index=True) #Indice simplifica buscas por nome
    monitoring_type = Column(PgEnum(MonitoringType, name="monitoring_type_enum"), nullable=False)

    #Para produtos via API (search_query) e scraping (product_url)
    search_query = Column(String, nullable=True, index=True)
    product_url = Column(Text, nullable=False)
    normalized_url = Column(Text, nullable=False, index=True)

    current_price = Column(Numeric(10,2), nullable=True)
    free_shipping = Column(Boolean, default=False)
    currency = Column(String(8), nullable=True)
    thumbnail = Column(Text, nullable=True)
    availability = Column(Boolean, nullable=True, default=True, server_default="true")
    last_status = Column(Text, nullable=True)

    #Flag indicando destaque manual exibido no dashboard
    is_featured = Column(Boolean, nullable=False, default=False, server_default="false")

    #Cache condicional
    etag = Column(String, nullable=True)
    last_modified = Column(DateTime(timezone=True), nullable=True)
    last_scrape_signature = Column(String, nullable=True)

    #Controle de status
    status = Column(PgEnum(MonitoredStatus, name="monitored_status_enum"), nullable=False, default=MonitoredStatus.active)
    paused = Column(Boolean, nullable=False, default=False, server_default="false")
    paused_at = Column(DateTime(timezone=True), nullable=True)
    last_checked = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_scraped_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_collection_reason = Column(String, nullable=True)
    # Contrato de estado de coleta (v1) — campos adicionados em f3b2d1e5a8c7
    collection_outcome = Column(String, nullable=True)
    collection_error_class = Column(String, nullable=True)
    collection_retryable = Column(Boolean, nullable=True)
    collection_next_retry_at = Column(DateTime(timezone=True), nullable=True)
    collection_source_integrity = Column(Boolean, nullable=True)
    collection_status_updated_at = Column(DateTime(timezone=True), nullable=True)
    collected_at = Column(DateTime(timezone=True), nullable=True)
    last_price_change_at = Column(DateTime(timezone=True), nullable=True)
    group_collected_at = Column(DateTime(timezone=True), nullable=True)
    check_interval = Column(Integer, nullable=True)
    stability_score = Column(Integer, nullable=True)
    next_check_at = Column(DateTime(timezone=True), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    #Relacionamento com CompetitorProduct
    competitors = relationship("CompetitorProduct", back_populates="monitored_product", cascade="all, delete-orphan")
    scraping_errors = relationship("ScrapingError", back_populates="product", cascade="all, delete-orphan", lazy="dynamic")
    price_history = relationship("PriceHistory", back_populates="monitored_product", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<MonitoredProduct("
            f"name_identification={self.name_identification},"
            f"user_id={self.user_id},"
            f"type={self.monitoring_type},"
            f"status={self.status}"
            f")>"
        )
    
    @property
    def display_name(self) -> str:
        """ Nome preparado para exibição em contratos simplificados """
        return self.name_identification
    

# ---------- PRODUTO CONCORRENTE ----------
class CompetitorProduct(Base):
    """ Produto concorrente usado para comparação e dependente do monitorado """

    __tablename__ = "competitor_products"

    __table_args__ = (
        #Duplicidades são avaliadas com base na URL original do usuário
        UniqueConstraint("monitored_product_id", "product_url", name="uq_competitor_url"),
    )

    #ID unico com UUIDv4
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Cascata no banco elimina concorrentes quando o monitorado é removido, evitando limpezas manuais
    monitored_product_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    #Dados do concorrente
    name_competitor = Column("name", String, nullable=False)
    product_url = Column(Text, nullable=False)

    current_price = Column(Numeric(10,2), nullable=True)
    old_price = Column(Numeric(10,2), nullable=True)
    free_shipping = Column(Boolean, default=False)
    seller = Column(String, nullable=True)
    seller_rating = Column(Float, nullable=True)
    currency = Column(String(8), nullable=True)
    thumbnail = Column(String, nullable=True)
    availability = Column(Boolean, nullable=True, default=True, server_default="true")
    last_status = Column(Text, nullable=True)

    #Cache condicional
    etag = Column(String, nullable=True)
    last_modified = Column(DateTime(timezone=True), nullable=True)

    #Controle de status
    status = Column(PgEnum(ProductStatus, name="product_status_enum"), nullable=False, default=ProductStatus.available)
    is_paused = Column(Boolean, nullable=False, default=False)
    last_checked = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_scraped_at = Column(DateTime(timezone=True), nullable=True, index=True)
    collected_at = Column(DateTime(timezone=True), nullable=True)
    last_price_change_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    #Relacionamento com MonitoredProduct
    monitored_product = relationship("MonitoredProduct", back_populates="competitors")
    price_history = relationship("PriceHistory", back_populates="competitor_product", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<CompetitorProduct("
            f"name_competitor={self.name_competitor},"
            f"price={self.current_price},"
            f"status={self.status}"
            f")>"
        )
    
    @property
    def display_name(self) -> str:
        """ Nome preparado para exibição em contratos simplificados """
        return self.name_competitor
