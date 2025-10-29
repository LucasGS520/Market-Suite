""" Facilita importações dos esquemas públicos do serviço 

O módulo mantém compatibilidade com consumidores legados expondo os
modelos ``ParserRequest`` e ``ParserResponse`` agora definidos no pacote
compartilhado. Dessa forma, testes e importações anteriores continuam
funcionando sem apontar diretamente para ``shared.schemas``.
"""

from shared.schemas.schemas_scraper import ParserRequest, ParserResponse
from .schemas_parse import ErrorResponse

__all__ = [
    "ParserRequest",
    "ParserResponse",
    "ErrorResponse",
]
