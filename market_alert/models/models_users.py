"""Definição do modelo de usuários com autenticação."""

import uuid

from sqlalchemy import Column, String, func, LargeBinary, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID #UUID e uuid.uuid4 gera identificadores unicos (id)
from sqlalchemy.orm import relationship

from infra.db import Base
from alert_app.core.password import hash_password, verify_password
from alert_app.models.models_refresh_token import RefreshToken


class User(Base):
    """ Usuário do sistema com autenticação local """

    __tablename__ = "users"

    #ID único com UUIDv4
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) #Chave primaria gerada automaticamente pelo UUId para cada novo user

    #Dados básicos
    name = Column(String(70), nullable=False) #Nome do usuário com até 70 caracteres e sendo um campo obrigatório
    email = Column(String(255), unique=True, index=True, nullable=False) #Email do usuário com até 255 caracteres, sendo um campo obrigatório e unico
    password = Column(LargeBinary, nullable=False) #Senha do usuário armazenado em formato binario

    #Segurança
    phone_number = Column(String(20), unique=True) #Numero de telefone do usuário ate 20 caracteres e unico
    is_active = Column(Boolean, default=True) #Usuario ativo ou bloqueado
    is_email_verified = Column(Boolean, default=False) #Verificação do email
    notifications_enabled = Column(Boolean, default=True)
    role = Column(String(20), default="user") #Função do usuário
    updated_by = Column(PG_UUID(as_uuid=True), nullable=True) #ID de quem atualizou o usuário

    #Controle de acesso
    last_login = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) #Ultimo login do usuário
    failed_attempts = Column(Integer, default=0, nullable=False)

    #Timestamp automáticos
    created_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) #Data em que o dia do login foi criado, gerando automaticamente
    updated_date = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False) #Data em que foi modificado o usuário atualizando automaticamente

    #Campos para verificação de email e recuperação de senha
    verification_token = Column(String, nullable=True)
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expires = Column(DateTime(timezone=True), nullable=True)

    #Relacionamento com Refresh Token
    refresh_tokens = relationship(RefreshToken, back_populates="user", cascade="all, delete-orphan")


    #Metodo para definir senha com hash
    def set_password(self, plain_password: str):
        """ Gera e armazena a senha como um hash binário"""
        self.password = hash_password(plain_password)

    #Metodo para verificar senha
    def check_password(self, plain_password: str) -> bool:
        """ Verifica se a senha informada corresponde ao hash armazenado """
        return verify_password(plain_password, self.password) #Retorna True ou False

    def __repr__(self):
        return f"<User(id={self.id}, name={self.name}, email={self.email})>"
