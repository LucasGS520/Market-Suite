""" Verifica a integração do scraper de produtos monitorados com as tarefas assíncronas de comparação """

import pytest
from unittest.mock import patch, Mock, AsyncMock
from uuid import uuid4
from decimal import Decimal
from sqlalchemy.orm import Session

from shared.schemas.schemas_products import MonitoredProductCreateScraping

try:
    from market_alert.services import services_scraper_monitored as mod
    scrape_monitored_product = mod.scrape_monitored_product
except Exception:
    pytestmark = pytest.mark.skip(reason="Dependências do market_alert indisponíveis")

def test_scrape_monitored_triggers_client_and_tasks():
    """ Garante integração entre cliente de scraping e tarefas de comparação """
    payload = MonitoredProductCreateScraping(
        #Campos obrigatórios requeridos pelo esquema compartilhado
        name_identification="Produto Teste",
        product_url="https://example.com/item",
        target_price=Decimal("10.00")
    )

    with patch.object(mod.ScraperClient, "parse", AsyncMock(return_value={
        "current_price": "10.00",
        "thumbnail": "img.jpg",
        "free_shipping": True
    })) as parse_mock, \
        patch("market_alert.services.services_scraper_monitored.create_or_update_monitored_product_scraped") as crud_mock, \
        patch("market_alert.tasks.compare_prices_tasks.compare_prices_task.delay") as delay_mock:

        crud_mock.return_value = type("Obj", (), {"id": uuid4()})()

        result = scrape_monitored_product(
            db=Mock(spec=Session),
            url=payload.product_url,
            user_id=uuid4(),
            payload=payload
        )

        parse_mock.assert_called_once()
        crud_mock.assert_called_once()
        delay_mock.assert_called_once()
        assert result["status"] == "success"
