""" Esquemas Pydantic para área de configurações do usuário """

from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SettingsProfileResponse(BaseModel):
    """ Representação do perfil de usuário exibida nas configurações """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    phone_number: Optional[str] = None
    email_verified: bool
    phone_number_verified: bool

class SettingsProfileUpdate(BaseModel):
    """ Payload para atualização do perfil dentro da tela de configurações """
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]):
        """ Valida se o nome informado possui caracteres válidos """
        if value is None:
            return value
        if not value.strip():
            raise ValueError("O nome não pode ser vazio.")
        if any(char.isdigit() for char in value):
            raise ValueError("O nome não pode conter números.")
        return value.strip()
    
    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: Optional[str]):
        """ Valida se o telefone possui dígitos suficientes """
        if value is None or value == "":
            return None
        if not re.fullmatch(r"\+?\d{10,15}", value):
            raise ValueError("Número de telefone inválido.")
        return value
    
class SettingsProfileUpdateResponse(BaseModel):
    """ Resposta de atualização do perfil com indicadores de verificação """
    profile: SettingsProfileResponse
    email_verification_required: bool = Field(False, description="Email alterado, requer verificação")
    phone_verification_required: bool = Field(False, description="Telefone alterado, requer verificação")

class NotificationSettings(BaseModel):
    """ Conjunto de preferências de canais de notificação do usuário """
    email: bool = Field(True, description="Canal de email habilitado")
    push: bool = Field(False, description="Canal de push habilitado")
    sms: bool = Field(False, description="Canal de SMS habilitado")
    whatsapp: bool = Field(False, description="Canal de WhatsApp habilitado")

class SettingsOverviewResponse(BaseModel):
    """ Resposta consolidada das configurações do usuário """
    profile: SettingsProfileResponse
    notifications: NotificationSettings
    