""" Esquemas Pydantic utilizados pela rota ``/parse`` """

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ParseRequest(BaseModel):
    """ Representa o corpo aceito pelo endpoint ``POST /parse`` """
    
    url: str = Field(..., description="URL pública do produto a ser analisado")

    @field_validator("url")
    @classmethod
    def _trim_url(cls, value: str) -> str:
        """ Remove espaços extras para padronizar o processamento """
        return value.strip()

class ParserResponse(BaseModel):
    """ Define o payload mínimo retornado após o sucesso do pipeline """

    name: str = Field(..., description="Nome identificado do produto")
    current_price: Decimal = Field(..., description="Preço atual do produto")
    url: str =  Field(..., description="URL normalizada na coleta")
    source: str = Field(..., description="Domínio de onde os dados foram obtidos")

class ErrorResponse(BaseModel):
    """ Padroniza mensagens de erro retornadas pela rota """
    
    message: str = Field(..., description="Descrição humanizada do erro")
    error_code: str = Field(..., description="Código categórico que identifica o erro encontrado")
    trace_id: str = Field(..., description="Identificador correlacionado com os logs estruturados")


__all__ = [
    "ParseRequest",
    "ParserResponse",
    "ErrorResponse",
]
