import pytest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException, status

from market_scraper.services import services_scraper_common as common
from market_scraper.services.synergic_pipeline import PipelineStep
from shared.enums import BlockResult


class ContadorSemRotulo:
    """ Implementa apenas incremento para uso em métricas sem rótulo """
    def __init__(self) -> None:
        self.total = 0

    def inc(self, valor: int = 1) -> None:
        """ Incrementa o contador interno pelo valor especificado """
        self.total += valor

class ContadorComRotulo(ContadorSemRotulo):
    """ Contador que registra combinações de rótulos utilizados """
    def __init__(self) -> None:
        super().__init__()
        self.rotulos: list[tuple] = []

    def labels(self, *rotulos: str, **rotulos_nomeados: str):
        """ Retém os rótulos fornecidos antes do incremento """
        if rotulos_nomeados:
            self.rotulos.append(tuple(rotulos_nomeados.items()))
        else:
            self.rotulos.append(tuple(rotulos_nomeados.items()))
        return self

def _configura_orquestrador(monkeypatch, retorno: dict) -> None:
    class OrquestradorFalso:
        async def scrape(self, **_: dict) -> dict:
            return retorno

    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", lambda *a, **k: OrquestradorFalso())
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)

@pytest.mark.asyncio
async def test_scrape_product_common_async_respeita_robots(monkeypatch):
    """ Ao receber bloqueio no robots.txt deve abortar e registrar métricas """
    contador_bloqueio = ContadorSemRotulo()
    contador_status = ContadorComRotulo()

    class ParserNegado:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        async def is_allowed(self, path: str, user_agent: str) -> bool:
            return False
        
        async def get_crawl_delay(self, user_agent: str) -> int | None:
            return None

    monkeypatch.setattr(common, "SCRAPER_HTTP_BLOCKED_TOTAL", contador_bloqueio)
    monkeypatch.setattr(common, "SCRAPER_URL_STATUS_TOTAL", contador_status)
    monkeypatch.setattr(common, "RobotsTxtParser", lambda base_url: ParserNegado(base_url))
    monkeypatch.setattr(common.ua_manager, "get_user_agent", lambda _: "AgenteTeste")
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")

    with pytest.raises(HTTPException) as exc:
        await common.scrape_product_common_async(
            url="https://exemplo.com/item",
            user_id=uuid4(),
            payload=payload,
            product_type="monitored",
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    assert contador_bloqueio.total == 1
    assert contador_status.total == 1
    assert dict(contador_status.rotulos[0]) == {"url_host": "exemplo.com", "status": "robots_blocked"}

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

    tocado = {"valor": False}

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: entrada_cache)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: tocado.__setitem__("valor", True))
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
    assert tocado["valor"] is True

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
        """ Estratégia que simula retorno ``NOT_MODIFIED`` """
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
            **kwargs,
        ):
            return {"status": "NOT_MODIFIED"}

    class StrategyShouldNotRun:
        """ Estratégia que não deve ser executada após ``NOT_MODIFIED`` """
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
            **kwargs,
        ):
            StrategyShouldNotRun.called = True
            return {"status": "success", "details": {"ok": True}}

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)

    monkeypatch.setattr(common, "strategies_for", lambda url, *, context="default": [StrategyNotModified(), StrategyShouldNotRun()])

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

class EtapaRetornoRapido(PipelineStep):
    """ Etapa fictícia que devolve dados válidos imediatamente """
    async def run (self, shared_context):
        return {
            "status": "success",
            "details": {"name": "Pipeline", "current_price": "99"},
            "extraction_method": "EtapaRetornoRapido",
        }
    
@pytest.mark.asyncio
async def test_scrape_product_common_async_pipeline_curto(monkeypatch):
    """ Pipeline retorna sucesso e evita chamada do orquestrador """
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    chamado = {"valor": False}

    class OrquestradorNaoChamado:
        def __init__(self, *a, **k):
            chamado["valor"] = True
        
        async def scrape(self, **k):
            return {"status": "error"}
        
    capturado: dict = {}

    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [EtapaRetornoRapido()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")
    monkeypatch.setattr(common.cache_manager, "set", lambda *, marketplace, url, value: capturado.update(value=value))
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", OrquestradorNaoChamado)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "Pipeline"
    assert chamado["valor"] is False
    assert capturado["value"]["data"]["current_price"] == "99"
    assert capturado["value"].get("metadata", {}).get("extraction_method") == "EtapaRetornoRapido"

@pytest.mark.asyncio
async def test_scrape_product_common_async_pipeline_not_modified(monkeypatch):
    """ Pipeline em NOT_MODIFIED utiliza cache e renova TTL """
    cached = {"data": {"name": "Cache", "current_price": "42"}}
    contador = {"vezes": 0}

    def _get_cache(*a, **k):
        contador["vezes"] += 1
        return cached if contador["vezes"] > 1 else None

    monkeypatch.setattr(common.cache_manager, "get", _get_cache)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    tocado = {"valor": False}
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: tocado.__setitem__("valor", True))

    class EtapaNotModified(PipelineStep):
        async def run(self, shared_context):
            return {"status": "NOT_MODIFIED"}
        
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [EtapaNotModified()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")
    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", lambda *a, **k: None)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "NOT_MODIFIED", "details": cached}
    assert tocado["valor"] is True
    
@pytest.mark.asyncio
async def test_scrape_product_common_async_pipeline_contexto_seguro(monkeypatch):
    """ Armazena apenas chaves de contexto seguro no cache """
    class EtapaContextoSeguro(PipelineStep):
        async def run(self, shared_context):
            shared_context["content_signature"] = "sig-123"
            shared_context["selectorlib_template"] = "produto.tpl"
            shared_context["token_sensivel"] = "nao deve aparecer"
            return {
                "status": "success",
                "details": {"name": "Pipeline", "current_price": "77"},
                "extraction_method": "EtapaContextoSeguro",
            }
    
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [EtapaContextoSeguro()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})

    capturado: dict = {}

    def _set_cache(*, marketplace, url, value, ttl=None):
        capturado["value"] = value

    monkeypatch.setattr(common.cache_manager, "set", _set_cache)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)

    class OrquestradorSentinela:
        instanciado = False

        def __init__(self, *a, **k):
            OrquestradorSentinela.instanciado = True

        async def scrape(self, **k):
            return {"status": "error"}
        
    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", OrquestradorSentinela)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert capturado["value"]["data"]["name"] == "Pipeline"
    assert capturado["value"]["metadata"]["extraction_method"] == "EtapaContextoSeguro"
    assert capturado["value"]["metadata"]["context"] == {
        "content_signature": "sig-123",
        "selectorlib_template": "produto.tpl",
    }
    assert "token_sensivel" not in capturado["value"]["metadata"]["context"]
    assert OrquestradorSentinela.instanciado is False

@pytest.mark.asyncio
async def test_scrape_product_common_async_respeita_crawl_delay(monkeypatch):
    """ Respeita o crawl delay antes de avançar para o pipeline """
    class ParserComDelay:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        async def is_allowed(self, path: str, user_agent: str) -> bool:
            return True
        
        async def get_crawl_delay(self, user_agent: str) -> int | None:
            return 2  #Segundos
    

    class EtapaBasica(PipelineStep):
        async def run(self, shared_context):
            return {
                "status": "success",
                "details": {"name": "Delay", "current_price": "11"},
            }
        
    sleep_registro = {"valor": 0}

    async def _fake_sleep(valor: int) -> None:
        sleep_registro["valor"] = valor

    monkeypatch.setattr(common, "RobotsTxtParser", lambda base_url: ParserComDelay(base_url))
    monkeypatch.setattr(common.ua_manager, "get_user_agent", lambda _: "AgenteTeste")
    monkeypatch.setattr(common.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [EtapaBasica()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "MultiStrategyScraperOrchestrator", lambda *a, **k: None)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert sleep_registro["valor"] == 2
