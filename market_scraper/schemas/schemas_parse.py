""" Esquemas Pydantic utilizados pela rota ``/parse`` """

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.schemas.schemas_scraper import ParserRequest as SharedParserRequest
from shared.schemas.schemas_scraper import ParserResponse as SharedParserResponse


class ParseRequest(SharedParserRequest):
    """ Especializa o contrato compartilhado para manter compatibilidade local """
    #Utilizamos herança direta para reaproveitar validações e garantir alinhamento

class ParserResponse(SharedParserResponse):
    """ Reflete o payload padrão devolvido pelo serviço de parsing """
    
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
