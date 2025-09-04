import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from decimal import Decimal
from sqlalchemy.orm import Session

from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping

from market_alert.services import services_scraper_monitored as monitored
from market_alert.services import services_scraper_competitor as competitor


@pytest.fixture
def fake_monitored_payload():
    return MonitoredProductCreateScraping(
        monitored_product_id=str(uuid4()),
        name_identification="Produto",
        product_url="http://teste",
        target_price=Decimal("10.00"),
    )

@pytest.fixture
def fake_competitor_payload():
    return CompetitorProductCreateScraping(
        monitored_product_id=str(uuid4()),
        product_url="http://teste",
    )

def _patch_monitored(monkeypatch):
    """ Aplica *patch* nas dependências do serviço de monitorados """
    parse_mock = AsyncMock(
        return_value={
            "current_price": "10.00",
            "thumbnail": "img.jpg",
            "free_shipping": True,
        }
    )
    close_mock = AsyncMock()
    monkeypatch.setattr(monitored.ScraperClient, "parse", parse_mock)
    monkeypatch.setattr(monitored.ScraperClient, "aclose", close_mock)

    crud_mock = Mock(return_value=type("Obj", (), {"id": uuid4()})())
    monkeypatch.setattr(monitored, "create_or_update_monitored_product_scraped", crud_mock)

    delay_mock = Mock()
    monkeypatch.setattr(monitored.compare_prices_task, "delay", delay_mock)
    return parse_mock, crud_mock, delay_mock, close_mock

def _patch_competitor(monkeypatch):
    """ Aplica *patch* nas dependências do serviço de concorrentes """
    parse_mock = AsyncMock(
        return_value={
            "name": "Teste",
            "current_price": "5.00",
            "old_price": "6.00",
            "thumbnail": "img.jpg",
            "free_shipping": False,
            "seller": "Loja",
        }
    )
    close_mock = AsyncMock()
    monkeypatch.setattr(competitor.ScraperClient, "parse", parse_mock)
    monkeypatch.setattr(competitor.ScraperClient, "aclose", close_mock)

    crud_mock = Mock(return_value=type("Obj", (), {"id": uuid4()})())
    monkeypatch.setattr(competitor, "create_or_update_competitor_product_scraped", crud_mock)

    return parse_mock, crud_mock, close_mock


# ----- TESTE PARA SERVIÇOS MONITORADO -----
def test_scrape_monitored_sync(monkeypatch, fake_monitored_payload):
    parse_mock, crud_mock, delay_mock, close_mock = _patch_monitored(monkeypatch)

    result = monitored.scrape_monitored_product(
        db=Mock(spec=Session),
        url=fake_monitored_payload.product_url,
        user_id=uuid4(),
        payload=fake_monitored_payload,
    )

    parse_mock.assert_awaited_once()
    crud_mock.assert_called_once()
    delay_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert result["status"] == "success"

@pytest.mark.asyncio
async def test_scrape_monitored_async(monkeypatch, fake_monitored_payload):
    parse_mock, crud_mock, delay_mock, close_mock = _patch_monitored(monkeypatch)

    result = await monitored.scrape_monitored_product_async(
        db=Mock(spec=Session),
        url=fake_monitored_payload.product_url,
        user_id=uuid4(),
        payload=fake_monitored_payload,
    )

    parse_mock.assert_awaited_once()
    crud_mock.assert_called_once()
    delay_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert result["status"] == "success"

# ----- TESTE PARA SERVIÇOS CONCORRENTE -----
def test_scrape_competitor_sync(monkeypatch, fake_competitor_payload):
    parse_mock, crud_mock, close_mock = _patch_competitor(monkeypatch)

    result = competitor.scrape_competitor_product(
        db=Mock(spec=Session),
        user_id=uuid4(),
        url=fake_competitor_payload.product_url,
        payload=fake_competitor_payload,
    )

    parse_mock.assert_awaited_once()
    crud_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert result["status"] == "success"

@pytest.mark.asyncio
async def test_scrape_competitor_async(monkeypatch, fake_competitor_payload):
    parse_mock, crud_mock, close_mock = _patch_competitor(monkeypatch)

    result = await competitor.scrape_competitor_product_async(
        db=Mock(spec=Session),
        user_id=uuid4(),
        url=fake_competitor_payload.product_url,
        payload=fake_competitor_payload,
    )

    parse_mock.assert_awaited_once()
    crud_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert result["status"] == "success"
