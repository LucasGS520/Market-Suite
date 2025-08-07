""" Modelo de dados para refresh tokens de sessão """

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from infra.db import Base


class RefreshToken(Base):
    """ Entidade de token de atualização usado no login """

    __tablename__ = "refresh_tokens"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(512), nullable=False)
    hashed_token = Column(String(128), nullable=False, unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)

    #Relacionamento de volta para usuário
    user = relationship("User", back_populates="refresh_tokens", lazy="joined")


    def is_expired(self) -> bool:
        """ Retorna True se o Token já expirou """
        return datetime.now(timezone.utc) >= self.expires_at

    def __repr__(self) -> str:
        return (
            f"<RefreshToken id={self.id} user_id={self.user_id} "
            f"expires_at={self.expires_at.isoformat()} revoked={self.revoked}>"
        )
