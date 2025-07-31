""" Esquemas Pydantic para respostas de erros durante o scraping """

from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.enums.enums_error_codes import ScrapingErrorType


class ScrapingErrorResponse(BaseModel):
    """ Esquema de resposta para erros de scraping """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    timestamp: datetime
    error_type: ScrapingErrorType
    message: str
