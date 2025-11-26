""" Facilita importações dos esquemas públicos do serviço 

O módulo mantém compatibilidade com consumidores legados expondo os
modelos centralizados em ``shared.schemas``. Dessa forma, testes e
importações anteriores continuam funcionando sem apontar diretamente
para o pacote compartilhado.
"""

from backend.shared.schemas.shared_schemas_scraper import ErrorResponse, ParserRequest, ParserResponse

__all__ = [
    "ParserRequest",
    "ParserResponse",
    "ErrorResponse",
]
