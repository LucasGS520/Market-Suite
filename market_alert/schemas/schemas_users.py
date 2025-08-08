""" Esquemas Pydantic para gerenciamento de usuários e validações """

import re
import uuid
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict


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

    #Valida o telefone (aceita DDD e 8 ou 9 dígitos)
    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value):
        """ Valida se o número de telefone tem entre 10 e 11 dígitos numéricos """
        if value and not re.fullmatch(r"\d{10,11}", value):
            raise ValueError("Número de telefone inválido, use apenas números")
        return value

#Classe de entrada para criação de usuários
class UserCreate(UserBase):
    """ Esquema para a criação de usuário (entrada na API)"""
    password: str #senha recebida em texto, mas será armazenada com hash
    notifications_enabled: bool = True

    #Valida senha com no mínimo 8 caracteres
    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        """ Valida senha com no mínimo 8 dígitos """
        if len(value) < 8:
            raise ValueError("A senha deve ter no mínimo 8 caracteres.")
        return value

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
    notifications_enabled: Optional[bool] = None

    #Valida se o nome não contem números
    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        """ Valida se o nome não possui números """
        if value and any(char.isdigit() for char in value):
            raise ValueError("O nome não pode conter números.")
        return value

    #Valida o telefone (aceita DDD e 8 ou 9 dígitos)
    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value):
        """ Valida se o número de telefone tem entre 10 e 11 dígitos numéricos """
        if value and not re.fullmatch(r"\d{10,11}", value):
            raise ValueError("Número de telefone inválido, use apenas números")
        return value

    model_config = ConfigDict(from_attributes=True)

#Esquema de respostas que serão retornados na API
class UserResponse(BaseModel):
    """Esquema de resposta para usuário (dados retornados pela API)"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    phone_number: Optional[str] = None
    is_active: bool
    is_email_verified: bool
    notifications_enabled: bool
    role: str
    last_login: Optional[datetime] = None
    created_date: datetime
    updated_date: datetime
