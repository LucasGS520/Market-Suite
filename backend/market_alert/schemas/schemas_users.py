""" Esquemas Pydantic para gerenciamento de usuários e validações """

import re
import uuid
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict

from market_alert.schemas.schemas_auth import password_validator


#Classe base para reutilizar atributos comuns
class UserBase(BaseModel):
    """ Esquema base para usuário (usado como herança)"""
    name: str
    email: EmailStr
    phone_number: Optional[str] = None

    #Valida se o nome não conte numeros
    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        """ Valida se o nome não possui números """
        if any(char.isdigit() for char in value):
            raise ValueError("O nome não pode conter números.")
        return value

    #Valida o telefone (aceita padrão E.164 ou números locais)
    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value):
        """ Valida se o número de telefone tem entre 10 e 15 dígitos """
        if value and not re.fullmatch(r"\+?\d{10,15}", value):
            raise ValueError("Número de telefone inválido")
        return value

#Classe de entrada para criação de usuários
class UserCreate(UserBase):
    """ Esquema para a criação de usuário (entrada na API)"""
    password: str #senha recebida em texto, mas será armazenada com hash

    #Valida senha exigindo complexidade mínima
    @field_validator("password", mode="before")
    @classmethod
    def validate_password(cls, value):
        """ Reutiliza a validação padrão de senha, garantindo letras e números """
        return password_validator(value)

#Esquema de entrada para Login
class UserLogin(BaseModel):
    """ Dados necessários para autenticação do usuário """
    email: EmailStr
    password: str

#Esquema para atualização de usuário
class UserUpdate(BaseModel):
    """ Campos permitidos para atualização parcial do usuário """
    name: Optional[str] = None
    phone_number: Optional[str] = None

    #Valida se o nome não contem números
    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        """ Valida se o nome não possui números """
        if value and any(char.isdigit() for char in value):
            raise ValueError("O nome não pode conter números.")
        return value

    #Valida o telefone no padrão E.164
    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value):
        """ Valida se o número de telefone segue o padrão E.164 """
        if value and not re.fullmatch(r"\+\d{10,15}", value):
            raise ValueError("Número de telefone inválido.")
        return value

    model_config = ConfigDict(from_attributes=True)

class VerificationResendRequest(BaseModel):
    """ Solicitação para reenviar verificação de email ou telefone """
    model_config = ConfigDict()

    channel: Literal["email", "phone_number"]

#Esquema de respostas que serão retornados na API
class UserResponse(BaseModel):
    """Esquema de resposta para usuário (dados retornados pela API)"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    phone_number: Optional[str] = None
    is_active: bool
    email_verified: bool
    email_verified_at: Optional[datetime] = None
    phone_number_verified: bool
    phone_verified_at: Optional[datetime] = None
    status: str
    role: str
    last_login: Optional[datetime] = None
    created_date: datetime
    updated_date: datetime
