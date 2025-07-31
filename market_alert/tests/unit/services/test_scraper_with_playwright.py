import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from decimal import Decimal
from sqlalchemy.orm import Session

from app.services.services_scraper_monitored import scrape_monitored_product
from app.schemas.schemas_products import MonitoredProductCreateScraping
from app.utils.playwright_client import PlaywrightClient


def test_scraper_monitored_uses_playwright(monkeypatch):
    html = "<html><body><h1>Produto Teste</h1></body></html>"

    payload = MonitoredProductCreateScraping(
        monitored_product_id=str(uuid4()),
        name_identification="Produto Teste",
        product_url="https://example.com/item",
        target_price=Decimal("10.00")
    )

    #Patches para evitar abrir o navegador real durante o teste
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_client(*_a, **_k):
        yield PlaywrightClient()

    with patch(
        "app.utils.playwright_client.PlaywrightClient.fetch_html",
        new=AsyncMock(return_value=html)
    ) as fetch_mock, \
        patch(
            "app.services.services_scraper_common.get_playwright_client",
            fake_client,
        ), \
        patch(
            "app.services.services_scraper_common.parser.looks_like_product_page",
            return_value=True
        ), \
        patch("app.services.services_scraper_common.parser.parse_product_details", return_value={
            "name": "Produto Teste",
            "current_price": "R$ 10,00",
            "old_price": None,
            "shipping": "Frete Grátis",
            "seller": "Loja X",
            "thumbnail": "img.jpg"
        }) as parse_mock, \
        patch("app.services.services_scraper_common.create_or_update_monitored_product_scraped") as crud_mock, \
        patch("app.tasks.compare_prices_tasks.compare_prices_task.delay") as delay_mock:

        crud_mock.return_value = type("Obj", (), {"id": "pid"})()

        result = scrape_monitored_product(
            db=Mock(spec=Session), url=payload.product_url, user_id=uuid4(), payload=payload
        )

        assert fetch_mock.await_count == 1
        parse_mock.assert_called_once_with(html, str(payload.product_url))
        crud_mock.assert_called_once()
        delay_mock.assert_called_once()
