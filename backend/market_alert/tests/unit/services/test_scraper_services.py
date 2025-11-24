""" Testes unitários dos serviços de scraping de monitorados e concorrentes """

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from backend.shared.schemas.shared_schemas_products import (
    CompetitorProductCreateScraping,
    MonitoredProductCreateScraping,
)
from backend.shared.schemas.shared_schemas_scraper import ParserResponse
from shared.utils.url_validation import canonicalize_product_url

from market_alert.enums.enums_products import MonitoredStatus
from market_alert.scraper.scraper_client import ScraperFetchResult
from market_alert.services import services_scraper_competitor as competitor
from market_alert.services import services_scraper_monitored as monitored


@pytest.fixture
def fake_monitored_payload() -> MonitoredProductCreateScraping:
    """ Cria payload de monitorado utilizado em diferentes cenários """
    return MonitoredProductCreateScraping(
        name_identification="Produto",
        product_url="http://teste",
    )

@pytest.fixture
def fake_competitor_payload() -> CompetitorProductCreateScraping:
    """ Cria payload de concorrente reaproveitado nos testes """
    return CompetitorProductCreateScraping(
        monitored_product_id=str(uuid4()),
        product_url="http://teste",
    )

def _build_parser_payload(**metadata) -> ParserResponse:
    """Monta resposta válida do scraper com metadados auxiliares"""

    default_payload = {
        "thumbnail": "img.jpg",
        "free_shipping": True,
        "currency": "BRL",
    }
    default_payload.update(metadata)
    return ParserResponse(
        name="Produto",
        current_price=Decimal("10.00"),
        payload=default_payload,
        source="test",
        url="http://teste",
    )


def _patch_monitored(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, Mock, AsyncMock]:
    """Prepara dependências dos serviços de monitorados"""

    fetch_result = ScraperFetchResult(
        status_code=200,
        payload=_build_parser_payload(),
        headers={"ETag": "abc", "Last-Modified": "Wed, 01 May 2024 12:00:00 GMT"},
    )
    fetch_mock = AsyncMock(return_value=fetch_result)
    close_mock = AsyncMock()
    monkeypatch.setattr(monitored.ScraperClient, "fetch", fetch_mock)
    monkeypatch.setattr(monitored.ScraperClient, "aclose", close_mock)

    crud_mock = Mock(return_value=SimpleNamespace(id=uuid4(), _price_changed=True, _availability_changed=False))
    monkeypatch.setattr(monitored, "create_or_update_monitored_product_scraped", crud_mock)
    monkeypatch.setattr(
        monitored,
        "get_monitored_product_by_user_and_url",
        Mock(return_value=None),
    )

    return fetch_mock, crud_mock, close_mock

def _patch_competitor(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, Mock, AsyncMock]:
    """Prepara dependências dos serviços de concorrentes"""

    fetch_result = ScraperFetchResult(
        status_code=200,
        payload=ParserResponse(
            name="Concorrente",
            current_price=Decimal("5.00"),
            payload={
                "thumbnail": "img.jpg",
                "free_shipping": False,
                "currency": "BRL",
            },
            url="http://teste",
            source="test",
        ),
        headers={"ETag": "xyz", "Last-Modified": "Wed, 01 May 2024 12:00:00 GMT"},
    )
    fetch_mock = AsyncMock(return_value=fetch_result)
    close_mock = AsyncMock()
    monkeypatch.setattr(competitor.ScraperClient, "fetch", fetch_mock)
    monkeypatch.setattr(competitor.ScraperClient, "aclose", close_mock)

    crud_mock = Mock(return_value=SimpleNamespace(id=uuid4(), _price_changed=True, _availability_changed=False))
    monkeypatch.setattr(competitor, "create_or_update_competitor_product_scraped", crud_mock)

    return fetch_mock, crud_mock, close_mock

# ----- TESTES PARA SERVIÇOS MONITORADOS -----

def test_scrape_monitored_sync(monkeypatch: pytest.MonkeyPatch, fake_monitored_payload: MonitoredProductCreateScraping) -> None:
    """Confere se o fluxo síncrono de monitorados persiste dados com sucesso"""

    fetch_mock, crud_mock, close_mock = _patch_monitored(monkeypatch)

    result = monitored.scrape_monitored_product(
        db=Mock(spec=Session),
        url=fake_monitored_payload.product_url,
        user_id=uuid4(),
        payload=fake_monitored_payload,
    )

    fetch_mock.assert_awaited_once()
    crud_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert result.status == "success"
    assert result.price_changed is True
    assert result.availability_changed is False
    assert result.price_changed is True
    assert result.availability_changed is False

@pytest.mark.asyncio
async def test_scrape_monitored_async(monkeypatch: pytest.MonkeyPatch, fake_monitored_payload: MonitoredProductCreateScraping) -> None:
    """Garante que a versão assíncrona chama o scraper e atualiza registros"""

    fetch_mock, crud_mock, close_mock = _patch_monitored(monkeypatch)

    result = await monitored.scrape_monitored_product_async(
        db=Mock(spec=Session),
        url=fake_monitored_payload.product_url,
        user_id=uuid4(),
        payload=fake_monitored_payload,
    )

    fetch_mock.assert_awaited_once()
    crud_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert result.status == "success"
    assert result.price_changed is True
    assert result.availability_changed is False
    assert result.price_changed is True
    assert result.availability_changed is False


@pytest.mark.asyncio
async def test_scrape_monitored_sanitiza_metadados(
    monkeypatch: pytest.MonkeyPatch,
    fake_monitored_payload: MonitoredProductCreateScraping,
) -> None:
    """ Metadados inseguros devem ser limpos antes de persistência """

    payload = ParserResponse(
        name="<b>Produto</b>",
        current_price=Decimal("10.00"),
        payload={
            "thumbnail": "javascript:alert('x')",
            "free_shipping": True,
            "currency": "<b>BRL</b>",
        },
        source="test",
        url="http://teste",
    )
    fetch_result = ScraperFetchResult(status_code=200, payload=payload, headers={})
    fetch_mock = AsyncMock(return_value=fetch_result)
    close_mock = AsyncMock()
    monkeypatch.setattr(monitored.ScraperClient, "fetch", fetch_mock)
    monkeypatch.setattr(monitored.ScraperClient, "aclose", close_mock)
    monkeypatch.setattr(
        monitored,
        "get_monitored_product_by_user_and_url",
        Mock(return_value=None),
    )

    captured: dict[str, object] = {}

    def _capture(*, scraped_info, currency, scraped_name, **kwargs):
        captured["thumbnail"] = scraped_info.thumbnail
        captured["currency_info"] = scraped_info.currency
        captured["currency_arg"] = currency
        captured["scraped_name"] = scraped_name
        return SimpleNamespace(id=uuid4(), _price_changed=False, _availability_changed=False)

    monkeypatch.setattr(monitored, "create_or_update_monitored_product_scraped", Mock(side_effect=_capture))

    result = await monitored.scrape_monitored_product_async(
        db=Mock(spec=Session),
        url=fake_monitored_payload.product_url,
        user_id=uuid4(),
        payload=fake_monitored_payload,
    )

    assert result.status == "success"
    assert result.price_changed is False
    assert result.availability_changed is False
    assert captured["thumbnail"] is None
    assert captured["currency_info"] == "BRL"
    assert captured["currency_arg"] == "BRL"
    assert captured["scraped_name"] == "Produto"

@pytest.mark.asyncio
async def test_scrape_monitored_async_propagates_last_modified(
    monkeypatch: pytest.MonkeyPatch,
    fake_monitored_payload: MonitoredProductCreateScraping,
) -> None:
    """Confere que o ``last_modified`` parseado é repassado para o CRUD"""

    _, crud_mock, _ = _patch_monitored(monkeypatch)

    await monitored.scrape_monitored_product_async(
        db=Mock(spec=Session),
        url=fake_monitored_payload.product_url,
        user_id=uuid4(),
        payload=fake_monitored_payload,
    )

    last_modified_arg = crud_mock.call_args.kwargs["last_modified"]
    assert last_modified_arg == datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)

@pytest.mark.asyncio
async def test_scrape_monitored_handles_not_modified(monkeypatch: pytest.MonkeyPatch, fake_monitored_payload: MonitoredProductCreateScraping) -> None:
    """Ao receber 304 o serviço deve apenas atualizar o ``last_checked``"""

    existing_id = uuid4()
    existing = SimpleNamespace(
        id=existing_id,
        last_checked=None,
        etag="old-etag",
        last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
        status=MonitoredStatus.active,
    )

    db = Mock(spec=Session)
    db.commit = Mock()

    fetch_mock = AsyncMock(
        return_value=ScraperFetchResult(status_code=304, payload=None, headers={"ETag": "abc"})
    )
    close_mock = AsyncMock()
    monkeypatch.setattr(monitored.ScraperClient, "fetch", fetch_mock)
    monkeypatch.setattr(monitored.ScraperClient, "aclose", close_mock)

    monkeypatch.setattr(
        monitored,
        "get_monitored_product_by_user_and_url",
        Mock(return_value=existing),
    )
    update_mock = Mock()
    monkeypatch.setattr(monitored, "create_or_update_monitored_product_scraped", update_mock)

    result = await monitored.scrape_monitored_product_async(
        db=db,
        url=fake_monitored_payload.product_url,
        user_id=uuid4(),
        payload=fake_monitored_payload,
    )

    fetch_mock.assert_awaited_once()
    fetch_kwargs = fetch_mock.await_args.kwargs
    assert fetch_kwargs["etag"] == existing.etag
    assert fetch_kwargs["last_modified"] == existing.last_modified
    update_mock.assert_not_called()
    db.commit.assert_called()
    assert existing.last_checked is not None
    assert result.status == "not_modified"
    assert result.product_id == str(existing_id)
    assert result.price_changed is False
    assert result.availability_changed is False

# ----- TESTES PARA SERVIÇOS DE CONCORRENTES -----

def test_scrape_competitor_sync(monkeypatch: pytest.MonkeyPatch, fake_competitor_payload: CompetitorProductCreateScraping) -> None:
    """Valida execução síncrona do scraping de concorrentes"""

    fetch_mock, crud_mock, close_mock = _patch_competitor(monkeypatch)

    result = competitor.scrape_competitor_product(
        db=Mock(spec=Session),
        user_id=uuid4(),
        url=fake_competitor_payload.product_url,
        payload=fake_competitor_payload,
    )

    fetch_mock.assert_awaited_once()
    crud_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert result.status == "success"

@pytest.mark.asyncio
async def test_scrape_competitor_async(monkeypatch: pytest.MonkeyPatch, fake_competitor_payload: CompetitorProductCreateScraping) -> None:
    """Garante que o fluxo assíncrono persiste informações de concorrentes"""

    fetch_mock, crud_mock, close_mock = _patch_competitor(monkeypatch)

    result = await competitor.scrape_competitor_product_async(
        db=Mock(spec=Session),
        user_id=uuid4(),
        url=fake_competitor_payload.product_url,
        payload=fake_competitor_payload,
    )

    fetch_mock.assert_awaited_once()
    crud_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert result.status == "success"

@pytest.mark.asyncio
async def test_scrape_competitor_handles_not_modified(monkeypatch: pytest.MonkeyPatch, fake_competitor_payload: CompetitorProductCreateScraping) -> None:
    """304 deve apenas atualizar ``last_checked`` do concorrente existente"""

    existing_id = uuid4()
    existing = SimpleNamespace(
        id=existing_id,
        etag="etag-old",
        last_modified=datetime(2024, 2, 1, tzinfo=timezone.utc),
        last_checked=None,
    )

    db = Mock(spec=Session)
    db.commit = Mock()

    fetch_mock = AsyncMock(
        return_value=ScraperFetchResult(status_code=304, payload=None, headers={"ETag": "xyz"})
    )
    close_mock = AsyncMock()
    monkeypatch.setattr(competitor.ScraperClient, "fetch", fetch_mock)
    monkeypatch.setattr(competitor.ScraperClient, "aclose", close_mock)

    monkeypatch.setattr(competitor, "_get_existing", Mock(side_effect=lambda *_, **__: existing))
    update_mock = Mock()
    monkeypatch.setattr(competitor, "create_or_update_competitor_product_scraped", update_mock)

    result = await competitor.scrape_competitor_product_async(
        db=db,
        user_id=uuid4(),
        url=fake_competitor_payload.product_url,
        payload=fake_competitor_payload,
    )

    fetch_mock.assert_awaited_once()
    fetch_kwargs = fetch_mock.await_args.kwargs
    assert fetch_kwargs["etag"] == existing.etag
    assert fetch_kwargs["last_modified"] == existing.last_modified
    update_mock.assert_not_called()
    db.commit.assert_called()
    assert existing.last_checked is not None
    assert result.status == "not_modified"
    assert result.product_id == str(existing_id)

@pytest.mark.asyncio
async def test_scrape_competitor_reutiliza_url_canonica(
    monkeypatch: pytest.MonkeyPatch,
    fake_competitor_payload: CompetitorProductCreateScraping,
) -> None:
    """ Variações da URL devem reaproveitar registro e cabeçalhos condicionais """

    raw_url = "HTTP://WWW.Example.com/produto//?ref=abc"
    normalized_url = canonicalize_product_url(raw_url)
    payload = fake_competitor_payload.model_copy(update={"product_url": raw_url})

    existing = SimpleNamespace(
        id=uuid4(),
        etag="etag-old",
        last_modified=datetime(2024, 2, 1, tzinfo=timezone.utc),
        last_checked=None,
    )

    db = Mock(spec=Session)
    db.commit = Mock()

    fetch_mock = AsyncMock(return_value=ScraperFetchResult(status_code=304, payload=None, headers={}))
    close_mock = AsyncMock()
    monkeypatch.setattr(competitor.ScraperClient, "fetch", fetch_mock)
    monkeypatch.setattr(competitor.ScraperClient, "aclose", close_mock)

    captured: dict[str, str] = {}

    def _capture_existing(db_arg: Session, normalized_payload: CompetitorProductCreateScraping, normalized: str):
        captured["payload_url"] = str(normalized_payload.product_url)
        captured["normalized_url"] = normalized
        return existing

    monkeypatch.setattr(competitor, "_get_existing", _capture_existing)
    monkeypatch.setattr(competitor, "create_or_update_competitor_product_scraped", Mock())

    result = await competitor.scrape_competitor_product_async(
        db=db,
        user_id=uuid4(),
        url=raw_url,
        payload=payload,
    )

    assert captured["payload_url"] == normalized_url
    assert captured["normalized_url"] == normalized_url
    fetch_kwargs = fetch_mock.await_args.kwargs
    assert fetch_kwargs["url"] == normalized_url
    assert fetch_kwargs["etag"] == existing.etag
    assert fetch_kwargs["last_modified"] == existing.last_modified
    db.commit.assert_called_once()
    assert result.status == "not_modified"
    assert result.product_id == str(existing.id)

@pytest.mark.asyncio
async def test_scrape_competitor_sanitiza_campos(
    monkeypatch: pytest.MonkeyPatch,
    fake_competitor_payload: CompetitorProductCreateScraping,
) -> None:
    """ Dados de concorrentes devem ser sanitizados antes do CRUD """

    response = ScraperFetchResult(
        status_code=200,
        payload=ParserResponse(
            name="<b>Concorrente</b>",
            current_price=Decimal("5.00"),
            payload={
                "thumbnail": "javascript:alert('x')",
                "seller": "<i>Loja</i>",
                "currency": "<b>BRL</b>",
            },
            url="http://teste",
            source="test",
        ),
        headers={},
    )

    fetch_mock = AsyncMock(return_value=response)
    close_mock = AsyncMock()
    monkeypatch.setattr(competitor.ScraperClient, "fetch", fetch_mock)
    monkeypatch.setattr(competitor.ScraperClient, "aclose", close_mock)

    captured: dict[str, object] = {}

    def _capture(*, scraped_info, currency, **kwargs):
        captured["name"] = scraped_info.name
        captured["thumbnail"] = scraped_info.thumbnail
        captured["seller"] = scraped_info.seller
        captured["currency_info"] = scraped_info.currency
        captured["currency_arg"] = currency
        return SimpleNamespace(id=uuid4(), _price_changed=False)

    monkeypatch.setattr(competitor, "create_or_update_competitor_product_scraped", Mock(side_effect=_capture))

    result = await competitor.scrape_competitor_product_async(
        db=Mock(spec=Session),
        user_id=uuid4(),
        url=fake_competitor_payload.product_url,
        payload=fake_competitor_payload,
    )

    assert result.status == "success"
    assert captured["name"] == "Concorrente"
    assert captured["thumbnail"] is None
    assert captured["seller"] == "Loja"
    assert captured["currency_info"] == "BRL"
    assert captured["currency_arg"] == "BRL"
    