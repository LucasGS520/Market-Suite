""" Funções CRUD para manipular produtos concorrentes """
from unicodedata import normalize
from uuid import UUID
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from alert_app.models.models_products import CompetitorProduct, MonitoredProduct
from utils.ml_url import canonicalize_ml_url
from alert_app.enums.enums_products import ProductStatus, MonitoringType
from alert_app.schemas.schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo


def create_or_update_competitor_product_scraped(db: Session, product_data: CompetitorProductCreateScraping, scraped_info: CompetitorScrapedInfo, last_checked: datetime) -> CompetitorProduct:
    """ Atualiza ou cria um produto concorrente a partir dos dados do scraping manual com link direto """
    canonical = canonicalize_ml_url(str(product_data.product_url))
    normalized_url = canonical or str(product_data.product_url)

    #Verifica se já existe um concorrente com mesmo monitored_product_id e URL
    existing = (
        db.query(CompetitorProduct)
        .filter(
            CompetitorProduct.monitored_product_id == product_data.monitored_product_id,
            CompetitorProduct.product_url == normalized_url
        )
        .first()
    )

    if existing:
        #Atualiza somente campos relevantes
        existing.old_price = existing.current_price
        existing.current_price = scraped_info.current_price
        existing.thumbnail = scraped_info.thumbnail
        existing.free_shipping = scraped_info.free_shipping
        existing.last_checked = last_checked
        existing.status = ProductStatus.available
        db.commit()
        db.refresh(existing)
        return existing

    #Caso não exista, cria um registro
    new = CompetitorProduct(
        monitored_product_id=product_data.monitored_product_id,
        name_competitor=scraped_info.name,
        product_url=normalized_url,
        current_price=scraped_info.current_price,
        old_price=scraped_info.old_price,
        free_shipping=scraped_info.free_shipping,
        seller=scraped_info.seller,
        seller_rating=scraped_info.seller_rating,
        thumbnail=scraped_info.thumbnail,
        status=ProductStatus.available,
        last_checked=last_checked
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return new

def get_all_competitor_products(db: Session) -> List[CompetitorProduct]:
    """ Retorna todos os produtos concorrentes cadastrados no banco """
    return db.query(CompetitorProduct).all()

def get_competitor_products_by_user(db: Session, user_id: UUID) -> List[CompetitorProduct]:
    """ Lista os concorrentes pertencentes a determinado usuário """
    return (
        db.query(CompetitorProduct)
        .join(MonitoredProduct)
        .filter(MonitoredProduct.user_id == user_id)
        .all()
    )

def get_competitor_products_by_type(db: Session, user_id: UUID, monitoring_type: MonitoringType) -> List[CompetitorProduct]:
    """ Retorna todos os produtos concorrentes vinculados ao tipo do produto monitorado (API ou Scraping) """
    return (
        db.query(CompetitorProduct)
        .join(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user_id,
            MonitoredProduct.monitoring_type == monitoring_type
        ).all()
    )

def get_competitors_by_monitored_id(db: Session, monitored_product_id: UUID) -> List[CompetitorProduct]:
    """ Lista todos os produtos concorrentes associados a um produto monitorado pelo ID """
    return (
        db.query(CompetitorProduct)
        .filter(CompetitorProduct.monitored_product_id == monitored_product_id)
        .all()
    )

def delete_competitors_by_monitored_id(db: Session, monitored_product_id: UUID) -> List[CompetitorProduct]:
    """ Remove todos os produtos concorrentes vinculados a um produto monitorado """
    competitors = get_competitors_by_monitored_id(db, monitored_product_id)
    for item in competitors:
        db.delete(item)
    db.commit()
    return competitors
