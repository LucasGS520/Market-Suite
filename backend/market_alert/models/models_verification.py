""" Modelo de dados para tokens de verificação de email e telefone """

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship

from shared.infra.db import Base
from market_alert.enums.enums_users import VerificationKind


class Verification(Base):
    """ Registro de verificação para email e telefone """

    __tablename__ = "verifications"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(Enum(VerificationKind, name="verification_kind"), nullable=False)
    token_hash = Column(String(128), nullable=True, index=True, unique=True)
    otp_hash = Column(String(128), nullable=True, index=True, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    attempts_remaining = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    meta = Column(JSONB, nullable=True)

    user = relationship("User", lazy="joined")

    def __repr__(self) -> str:
        return f"<Verification id={self.id} user_id={self.user_id} kind={self.kind} expires_at={self.expires_at.isoformat()}>"
    