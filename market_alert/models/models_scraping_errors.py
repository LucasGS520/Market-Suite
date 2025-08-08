""" Modelos com informações de erro de scraping """

import uuid
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, ForeignKey, Integer, String, Enum as PgEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session, relationship

from infra.db import Base
from alert_app.enums.enums_error_codes import ScrapingErrorType


class ScrapingError(Base):
    """ Registro de falhas ocorridas durante o scraping """

    __tablename__ = "scraping_errors"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(PG_UUID(as_uuid=True), ForeignKey("monitored_products.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(Text, nullable=False)

    stage = Column(String(50), nullable=False, default="unknown")

    http_status = Column(Integer, nullable=True)

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    error_type = Column(PgEnum(ScrapingErrorType, name="scraping_error_type_enum"), nullable=False, default=ScrapingErrorType.missing_data)
    message = Column(Text, nullable=True)

    product = relationship("MonitoredProduct", back_populates="scraping_errors", lazy="joined")


    def __repr__(self) -> str:
        msg_preview = (self.message[:30] + "...") if self.message and len(self.message) > 30 else self.message
        return (
            f"<ScrapingError(id={self.id} product_id={self.product_id} "
            f"url={self.url!r} type={self.error_type} ts={self.timestamp} "
            f"msg={msg_preview})>"
        )


    @classmethod
    def create(cls, db: Session, product_id: UUID, url: str, error_type: ScrapingErrorType, message: str | None = None, stage: str = "error", http_status: int | None = None):
        """ Cria e persiste um registro de erro de scraping """
        error = cls(
            product_id=product_id,
            url=url,
            stage=stage,
            http_status=http_status,
            error_type=error_type,
            message=message
        )
        db.add(error)
        db.commit()
        db.refresh(error)

        #Verifica erros recorrentes e notifica o time interno
        count = (
            db.query(cls)
            .filter(cls.product_id == product_id)
            .count()
        )
        if count >= 5:
            import structlog
            logger = structlog.get_logger("scraping_errors")
            logger.warning("persistent_scraping_errors", product_id=str(product_id), count=count)
        return error
