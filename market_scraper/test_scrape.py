import sys
from uuid import UUID, uuid4
from decimal import Decimal

from infra.db import SessionLocal
from scraper_app.services.services_scraper_monitored import scrape_monitored_product
from scraper_app.schemas.schemas_products import MonitoredProductCreateScraping


def main() -> None:
    """ Executa o scraping de forma isolada """
    if len(sys.argv) < 4:
        print("Usage: python test_scrape.py <url> <name> <target_price> [user_id]")
        sys.exit(1)

    url = sys.argv[1]
    name = sys.argv[2]
    target_price = Decimal(sys.argv[3])
    user_id = UUID(sys.argv[4]) if len(sys.argv) > 4 else uuid4()

    payload = MonitoredProductCreateScraping(
        name_identification=name,
        product_url=url,
        target_price=target_price
    )

    with SessionLocal() as db:
        result = scrape_monitored_product(db=db, url=url, user_id=user_id, payload=payload)
        print(result)

if __name__ == "__main__":
    main()

"""
Exemplo de comando: docker compose -f docker-compose.yml exec api python test_scrape.py "URL REAL" "tablet test" 799.90
"""
