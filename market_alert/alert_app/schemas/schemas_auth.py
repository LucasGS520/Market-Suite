""" Esquemas Pydantic utilizados em operações de autenticação e segurança """

import re
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator


def password_validator(value: str) -> str:
    """ Valida se a senha tem pelo menos 8 caracteres e contem letras e números """
    if len(value) < 8:
        raise ValueError("A senha deve ter ao menos 8 caracteres")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("A senha deve conter letras e números")
    return value


# ---------- RESPONSES DE TOKENS ----------

class TokenResponse(BaseModel):
    """ Esquema de resposta contendo o JWT de acesso """
    model_config = ConfigDict(from_attributes=True)

    access_token: str = Field(..., description="JWT de acesso do usuário")
    token_type: str = Field("bearer", description="Tipo de token, geralmente 'bearer'")

class TokenPairResponse(BaseModel):
    """ Retorno de par de tokens: Access + Refresh """
    model_config = ConfigDict(from_attributes=True)

    access_token: str = Field(..., description="JWT de acesso do usuário")
    refresh_token: str = Field(..., description="Refresh Token para obter novos access tokens")
    token_type: str = Field("bearer", description="Tipo de token, geralmente 'bearer'")


# ---------- REQUESTS DE AUTH ----------

class RefreshRequest(BaseModel):
    """ Payload para trocar um Refresh Token por um novo par de tokens """
    model_config = ConfigDict()

    refresh_token: str = Field(..., description="Refresh Token previamente emitido")


# ---------- FLUXOS DE E-MAIL & SENHA ----------

class EmailTokenRequest(BaseModel):
    """ Esquema para enviar ou confirmar tokens via e-mail """
    model_config = ConfigDict()

    token: str = Field(..., min_length=6, description="Token gerado para verificação ou reset")


class ResetPasswordRequest(BaseModel):
    """ Esquema para solicitar reset da senha """
    model_config = ConfigDict()

    email: EmailStr = Field(..., description="E-mail cadastrado no sistema para reset da senha")


class ResetPasswordConfirmRequest(BaseModel):
    """ Esquema para confirmar reset de senha utilizando token """
    model_config = ConfigDict()

    token: str = Field(..., description="Token de reset enviado por e-mail")
    new_password: str = Field(..., description="Nova senha do usuário")

    @field_validator("new_password", mode="before")
    @classmethod
    def check_password(cls, v):
        """ Aplica as validações de senha antes de salvar """
        return password_validator(v)


class ChangePasswordRequest(BaseModel):
    """ Esquema para alteração de senha pelo usuário autenticado """
    model_config = ConfigDict()

    old_password: str = Field(..., description="Senha atual do usuário")
    new_password: str = Field(..., description="Nova senha desejada")

    @field_validator("new_password", mode="before")
    @classmethod
    def check_password(cls, v):
        """ Aplica as validações de senha antes de salvar """
        return password_validator(v)


class ChangeEmailRequest(BaseModel):
    """ Esquema para alteração de email pelo usuário autenticado """
    model_config = ConfigDict()

    new_email: EmailStr = Field(..., description="Novo e-mail que será vinculado à conta")
