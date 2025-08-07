""" CRUD responsável pelo registro de erros de scraping """

from uuid import UUID
from sqlalchemy.orm import Session
from alert_app.models.models_scraping_errors import ScrapingError
from alert_app.enums.enums_error_codes import ScrapingErrorType

def create_scraping_error(db: Session, product_id: UUID, url: str, message: str, error_type: ScrapingErrorType) -> ScrapingError:
    """ Grava um erro de scraping ocorrido durante a coleta de preços """
    err = ScrapingError(product_id=product_id, url=url, message=message, error_type=error_type)
    db.add(err)
    db.commit()
    db.refresh(err)
    return err

def get_recent_scraping_errors(db: Session, limit: int = 50):
    """ Retorna os erros mais recentes ordenados por data """
    return (
        db.query(ScrapingError)
        .order_by(ScrapingError.timestamp.desc())
        .limit(limit)
        .all()
    )

def get_scraping_errors_for_product(db: Session, product_id: UUID, limit: int = 50):
    """ Retorna erros de scraping para um produto específico """
    return (
        db.query(ScrapingError)
        .filter(ScrapingError.product_id == product_id)
        .order_by(ScrapingError.timestamp.desc())
        .limit(limit)
        .all()
    )
