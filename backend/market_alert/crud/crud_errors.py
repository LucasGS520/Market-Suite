""" CRUD responsável pelo registro de erros de scraping """

from uuid import UUID
from sqlalchemy.orm import Session
from shared.enums.error_codes import ScrapingErrorType
from market_alert.models.models_scraping_errors import ScrapingError


def create_scraping_error(db: Session, product_id: UUID, url: str, message: str, error_type: ScrapingErrorType) -> ScrapingError:
    """ Grava um erro de scraping ocorrido durante a coleta de preços """
    err = ScrapingError(product_id=product_id, url=url, message=message, error_type=error_type)
    db.add(err)
    db.commit()
    db.refresh(err)
    return err
