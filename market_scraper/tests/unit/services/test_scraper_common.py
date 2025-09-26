""" Testes para a função `scrape_product_common_async` utilizando apenas o pipeline """

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from market_scraper.services import services_scraper_common as common
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
            self.rotulos.append(rotulos)
        return self

class PipelineSimulado:
    """ Pipeline falso para retornar resultados controlados """
    def __init__(self, *, resultado: dict):
        self.resultado = resultado
        self.execocoes = 0

    async def run(self, shared_context: dict) -> dict:
        """ Registra a execução e devolve o resultado configurado """
        self.execocoes += 1
        return self.resultado

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
    monkeypatch.setattr(common.identity_manager, "get_user_agent", lambda session, host=None: "AgenteTeste")
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)

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

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: entrada_cache)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    tocado = {"valor": False}
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: tocado.__setitem__("valor", True))
    
    def _pipeline_nao_chaamado(*args, **kwargs):
        raise AssertionError("Pipeline não deveria ser instanciado com cache válido")
    
    monkeypatch.setattr(common, "SynergicPipeline", _pipeline_nao_chaamado)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert resultado["details"] == dados_cache
    assert tocado["valor"] is True

@pytest.mark.asyncio
async def test_scrape_product_common_async_cache_invalido(monkeypatch):
    """ Ignora cache inválido e utiliza o pipeline para obter dados válidos """

    cache_invalido = {"data": {"name": "Produto", "current_price": None}}
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: cache_invalido)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})

    resultado_pipeline = {
        "results": [
            {
                "status": "success",
                "details": {"name": "Válido", "current_price": "10"},
                "extraction_method": "Teste",
            }
        ],
        "shared_context": {},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "Válido"
    assert pipeline_falso.execocoes == 1

@pytest.mark.asyncio
async def test_scrape_product_common_async_success_persiste_cache(monkeypatch):
    """ Ao obter dados válidos pelo pipeline deve persistir no cache com metadados """
    
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

    resultado_pipeline = {
        "results": [
            {
                "status": "success",
                "details": {"name": "Produto", "current_price": "10"},
                "extraction_method": "EtapaFalsa",
            }
        ],
        "shared_context": {"content_signature": "sig"},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {"etag": "e1", "last_modified": "11"})

    capturado: dict = {}

    def _set_cache(*, marketplace, url, value, ttl=None):
        capturado["value"] = value

    monkeypatch.setattr(common.cache_manager, "set", _set_cache)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert capturado["value"]["data"]["current_price"] == "10"
    assert capturado["value"]["metadata"]["extraction_method"] == "EtapaFalsa"
    assert capturado["value"]["metadata"]["context"] == {"content_signature": "sig"}


@pytest.mark.asyncio
async def test_scrape_product_common_async_pipeline_invalido(monkeypatch):
    """ Retorna erro detalhado quando o pipeline não valida os dados """
    
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

    resultado_pipeline = {
        "results": [
            {
                "status": "success",
                "details": {"current_price": "10"},
                "extraction_method": "EtapaIncompleta",
            }
        ],
        "shared_context": {},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)
    chamada_cache = {"valor": 0}

    def _registrar_cache(*a, **k):
        chamada_cache["valor"] += 1

    monkeypatch.setattr(common.cache_manager, "set", _registrar_cache)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"
    assert resultado["detail"] == "Nenhuma etapa do pipeline obteve dados válidos"
    assert chamada_cache["valor"] == 0

@pytest.mark.asyncio
async def test_scrape_product_common_async_bloqueia_cache_invalido(monkeypatch):
    """ Quando o pipeline retorna dados inválidos não deve persistir no cache """
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})

    resultado_pipeline = {
        "results": [
            {
                "status": "success",
                "details": {"name": "Produto", "current_price": "10"},
                "extraction_method": "EtapaFalsa",
            }
        ],
        "shared_context": {},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)

    chamada_cache = {"valor": 0}

    def _registrar_cache(*a, **k):
        chamada_cache["valor"] += 1

    monkeypatch.setattr(common.cache_manager, "set", _registrar_cache)

    class validadorSequencial:
        """ Simula validador que falha apenas na persistência """
        def __init__(self) -> None:
            self.chamadas = 0

        def validate(self, data: dict) -> None:
            self.chamadas += 1
            if self.chamadas == 2:
                raise ValueError("Falha na validação tardia")
            
    validador = validadorSequencial()
    monkeypatch.setattr(common, "validator", validador)
    monkeypatch.setattr(common.pre_pipeline_orchestrator, "validator", validador)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"
    assert resultado["detail"] == "Nenhuma etapa do pipeline obteve dados válidos"
    assert chamada_cache["valor"] == 0

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

    resultado_pipeline = {
        "results": [
            {
                "status": "NOT_MODIFIED",
            }
        ],
        "shared_context": {},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

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
async def test_scrape_product_common_async_pipeline_not_modified_sem_cache(monkeypatch):
    """ Quando não há cache a resposta mantém apenas o status NOT_MODIFIED """
    
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

    resultado_pipeline = {
        "results": [],
        "status": "NOT_MODIFIED",
        "shared_context": {},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "NOT_MODIFIED"}

@pytest.mark.asyncio
async def test_scrape_product_common_async_pipeline_desabilitado(monkeypatch):
    """ Feature flag desabilitada deve retornar erro imediato """

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

    contador_flags = ContadorComRotulo()
    monkeypatch.setattr(common, "SCRAPER_FEATURE_FLAG_TOTAL", contador_flags)

    monkeypatch.setattr(
        common,
        "evaluate_feature_flag",
        lambda *a, **k: SimpleNamespace(
            enabled=False,
            rollout_percentage=0.0,
            source="teste",
            bucket_value=None,
        ),
    )

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "error"
    assert ("synergic_pipeline", "disabled") in contador_flags.rotulos


@pytest.mark.asyncio
async def test_scrape_product_common_async_sem_etapas(monkeypatch):
    """ Quando nenhuma etapa está configurada o serviço deve retornar erro """

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda url: [])

    contador_flags = ContadorComRotulo()
    monkeypatch.setattr(common, "SCRAPER_FEATURE_FLAG_TOTAL", contador_flags)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "error", "detail": "Pipeline não configurado para o domínio"}
    assert ("synergic_pipeline", "no_steps") in contador_flags.rotulos

@pytest.mark.asyncio
async def test_scrape_product_common_async_status_especial(monkeypatch):
    """ Status especiais retornados pelo pipeline devem ser propagados  """

    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

    resultado_pipeline = {
        "results": [],
        "status": BlockResult.CAPTCHA.value,
        "shared_context": {},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)

    contador_bloqueio = ContadorComRotulo()
    monkeypatch.setattr(common, "SCRAPER_HTTP_BLOCKED_TOTAL", contador_bloqueio)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": BlockResult.CAPTCHA.value}
    assert contador_bloqueio.total == 1

@pytest.mark.asyncio
async def test_scrape_product_common_async_pipeline_falha(monkeypatch):
    """ Quando nenhuma etapa produz dados o retorno deve cnonter mensagem amigável """
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

    resultado_pipeline = {
        "results": [
            {"status": "error", "detail": "sem dados"},
            {"status": "error"},
        ],
        "shared_context": {},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado == {"status": "error", "detail": "sem dados"}

@pytest.mark.asyncio
async def test_scrape_product_common_async_respeita_crawl_delay(monkeypatch):
    """ Respeita o crawl delay antes de avançar para o pipeline """
    class ParserComDelay:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        async def is_allowed(self, path: str, user_agent: str) -> bool:
            return True
        
        async def get_crawl_delay(self, user_agent: str) -> int | None:
            return 2
    
    sleep_registro = {"valor": 0}

    async def _fake_sleep(valor: int) -> None:
        sleep_registro["valor"] = valor

    monkeypatch.setattr(common, "RobotsTxtParser", lambda base_url: ParserComDelay(base_url))
    monkeypatch.setattr(common.identity_manager, "get_user_agent", lambda session, host=None: "AgenteTeste")
    monkeypatch.setattr(common.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(common.cache_manager, "get", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "set", lambda *a, **k: None)
    monkeypatch.setattr(common.cache_manager, "touch", lambda *a, **k: None)
    monkeypatch.setattr(common, "pipeline_steps_for", lambda *a, **k: [object()])
    monkeypatch.setattr(common, "pipeline_execution_mode_for", lambda *a, **k: "sequential")

    resultado_pipeline = {
        "results": [
            {
                "status": "success",
                "details": {"name": "Delay", "current_price": "11"},
                "extraction_method": "EtapaDelay",
            }
        ],
        "shared_context": {},
    }

    pipeline_falso = PipelineSimulado(resultado=resultado_pipeline)
    monkeypatch.setattr(common, "SynergicPipeline", lambda *a, **k: pipeline_falso)
    monkeypatch.setattr(common, "get_cache_headers", lambda url: {})

    payload = SimpleNamespace(product_url="https://exemplo.com/item")
    resultado = await common.scrape_product_common_async(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=payload,
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert sleep_registro["valor"] == 2
