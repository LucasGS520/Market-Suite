import pytest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from market_scraper.services import services_scraper_common as common
from shared.enums import BlockResult


def _configura_orquestrador(monkeypatch, retorno: dict) -> None:
    class OrquestradorFalso:
        async def scrape(self, **_: dict) -> dict:
            return retorno

    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", lambda *a, **k: OrquestradorFalso())
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)

@pytest.mark.asyncio
async def test_scrape_product_common_async_cached(monkeypatch):
    """ Deve usar o cache e evitar a chamada do orquestrador """
    dados_cache = {"name": "Produto Cache", "current_price": "50"}
    entrada_cache = {"data": dados_cache, "headers": {"etag": "abc"}}

    class OrquestradorRegistro:
        instanciado = False
        scrape_chamado = False

        def __init__(self, *_, **__):
            OrquestradorRegistro.instanciado = True

        async def scrape(self, **k):
            OrquestradorRegistro.scrape_chamado = True
            return {"status": "error"}

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: entrada_cache)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", OrquestradorRegistro)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert resultado["details"] == dados_cache
    assert OrquestradorRegistro.instanciado is False
    assert OrquestradorRegistro.scrape_chamado is False

@pytest.mark.asyncio
async def test_scrape_product_common_async_cache_incompleto(monkeypatch):
    """ Ignora cache inválido e aciona o orquestrador """
    cache_invalido = {"data": {"name": "Produto", "current_price": None}}

    class OrquestradorRegistro:
        chamado = False

        async def scrape(self, **k):
            OrquestradorRegistro.chamado = True
            return {"status": "success", "details": {"name": "Válido", "current_price": "10"}}

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: cache_invalido)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})
    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", lambda *a, **k: OrquestradorRegistro())

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "Válido"
    assert OrquestradorRegistro.chamado is True

@pytest.mark.asyncio
async def test_scraper_product_common_async_success(monkeypatch):
    """ Deve retornar sucesso quando o orquestrador indica dados válidos """
    _configura_orquestrador(monkeypatch, {"status": "success", "details": {"name": "Produto", "current_price": "10"}})
    capturado: dict = {}
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": "e1", "last_modified": "11"})
    monkeypatch.setattr(common.cache_manager, "set", lambda *, marketplace, url, value, ttl=None: capturado.update(value=value))

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert resultado["details"]["current_price"] == "10"
    assert capturado["value"]["headers"] == {"etag": "e1", "last_modified": "11"}

@pytest.mark.asyncio
async def test_scraper_product_common_async_success_sem_headers(monkeypatch):
    """ Não deve adicionar cabeçalhos ao cache quando inexistente """
    _configura_orquestrador(monkeypatch, {"status": "success", "details": {"name": "Produto", "current_price": "10"}})

    capturado: dict = {}

    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": None, "last_modified": None})

    def _set_cache(*, marketplace, url, value, ttl=None):
        capturado["value"] = value

    monkeypatch.setattr(common.cache_manager, "set", _set_cache)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert "headers" not in capturado["value"]

@pytest.mark.asyncio
async def test_scraper_product_common_async_missing_field(monkeypatch):
    """ Retorna erro detalhado quando campo essencial está ausente """
    _configura_orquestrador(monkeypatch, {"status": "success", "details": {"current_price": "10"}})
    set_chamado = False

    def _set_mock(*, marketplace, url, value, ttl=None):
        nonlocal set_chamado
        set_chamado = True

    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})
    monkeypatch.setattr(common.cache_manager, "set", _set_mock)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"
    assert "Campo obrigatório" in resultado["detail"]
    assert set_chamado is False

@pytest.mark.asyncio
async def test_scrape_product_common_async_missing_details(monkeypatch):
    """ Retorna erro quando o orquestrador não fornece dados """
    _configura_orquestrador(monkeypatch, {"status": "success", "details": None})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "error", "detail": "Dados do produto ausentes"}

@pytest.mark.asyncio
async def test_scrape_product_common_async_timeout(monkeypatch):
    """ Deve retornar erro quando a estratégia falha """

    _configura_orquestrador(monkeypatch, {"status": "error"})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"
    assert resultado["detail"] == "Falha ao coletar dados do scraping"

@pytest.mark.asyncio
async def test_scrape_product_common_async_detail_propagado(monkeypatch):
    """ Propaga detalhe específico de erro """
    _configura_orquestrador(monkeypatch, {"status": "error", "detail": "falha"})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "error", "detail": "falha"}

@pytest.mark.asyncio
async def test_scrape_product_common_async_orquestrador_exception(monkeypatch):
    """ Captura exceção inesperada do orquestrador """
    class OrqFalho:
        async def scrape(self, **k):
            raise RuntimeError("quebrou")
        
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", lambda *a, **k: OrqFalho())

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"
    assert "quebrou" in resultado["detail"]

@pytest.mark.asyncio
async def test_scrape_product_common_async_not_modified_breaks(monkeypatch):
    class StrategyNotModified:
        def supports_url(self, url):
            return True

        async def get_data(
            self,
            *,
            url,
            headers,
            user_id,
            payload,
            product_type,
            rate_limiter,
            circuit_breaker,
            recovery_manager,
            throttle_manager,
        ):
            return {"status": "NOT_MODIFIED"}

    class StrategyShouldNotRun:
        called = False

        def supports_url(self, url):
            return True

        async def get_data(
            self,
            *,
            url,
            headers,
            user_id,
            payload,
            product_type,
            rate_limiter,
            circuit_breaker,
            recovery_manager,
            throttle_manager,
        ):
            StrategyShouldNotRun.called = True
            return {"status": "success", "details": {"ok": True}}

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)

    monkeypatch.setattr(common, "strategies_for", lambda url: [StrategyNotModified(), StrategyShouldNotRun()])

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "NOT_MODIFIED"
    assert StrategyShouldNotRun.called is False

@pytest.mark.asyncio
async def test_scrape_product_common_async_captcha_detected(monkeypatch):
    """ Retorna CAPTCHA quando o orquestrador detecta bloqueio """

    _configura_orquestrador(monkeypatch, {"status": BlockResult.CAPTCHA.value})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": BlockResult.CAPTCHA.value}

@pytest.mark.asyncio
async def test_scrape_product_common_async_not_price(monkeypatch):
    """ Retorna erro quando o preço não é encontrado """

    _configura_orquestrador(monkeypatch, {"status": "error"})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"

@pytest.mark.asyncio
async def test_scrape_product_common_async_not_modified(monkeypatch):
    """ Retorna NOT_MODIFIED quando o conteúdo não mudou """

    _configura_orquestrador(monkeypatch, {"status": "NOT_MODIFIED"})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "NOT_MODIFIED"}

@pytest.mark.asyncio
async def test_scrape_product_common_async_not_modified_com_cache(monkeypatch):
    """ Retorna NOT_MODIIFED anexando dados do cache quando existentes """
    _configura_orquestrador(monkeypatch, {"status": "NOT_MODIFIED"})

    dados_cache = {"name": "Produto Cache", "current_price": "50"}
    entrada_cache = {"data": dados_cache}

    contador = {"vezes": 0}

    def _get_cache(*_, **__):
        contador["vezes"] += 1
        #Retorna None na primeira chamada (pré-orquestrador) e o cache na segunda
        return entrada_cache if contador["vezes"] > 1 else None
    
    monkeypatch.setattr(common.cache_manager, "get", _get_cache)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "NOT_MODIFIED"
    assert resultado["details"] == entrada_cache