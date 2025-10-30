""" Esquemas Pydantic utilizados pela rota ``/scraper/parse`` """

from __future__ import annotations

from pydantic import BaseModel, Field

    
class ErrorResponse(BaseModel):
    """ Padroniza mensagens de erro retornadas pela rota """
    message: str = Field(..., description="Descrição humanizada do erro")
    error_code: str = Field(..., description="Código categórico que identifica o erro encontrado")
    trace_id: str = Field(..., description="Identificador correlacionado com os logs estruturados")


__all__ = [
    "ErrorResponse",
]
