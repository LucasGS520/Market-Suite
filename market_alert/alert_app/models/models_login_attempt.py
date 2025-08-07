""" Modelo para registrar tentativas de login dos usuários """

import structlog
from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from uuid import uuid4

from infra.db import Base


#Logger para rastrear atividades do modelo de tentativas de login
logger = structlog.get_logger("model.login_attempt")

class LoginAttempt(Base):
    """ Representa uma tentativa de login realizada por um usuário """

    __tablename__ = "login_attempts"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False)
    status = Column(String(30), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        """ Retorna uma representação em string da tentativa """
        return (
            f"<LoginAttempt id={self.id} email={self.email}"
            f"ip={self.ip_address} status={self.status} timestamp={self.timestamp}>"
        )
