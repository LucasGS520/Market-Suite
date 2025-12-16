""" Testes de integração isolados para as tasks de scraping """

import pickle
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.market_alert.scraper.scraper_client import ScraperClientError
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult
from shared.exceptions import ScraperError
from market_alert.tasks.scraper_tasks import collect_competitor_task, collect_product_task


class DummySession:
    """ Gerente de contexto simples emulando uma sessão SQLAlchemy """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        pass

    def add(self, *_args, **__kwargs):
        return None
    
    def commit(self):
        return None
    
    def refresh(self, *_args, **__kwargs):
        return None

#UUID válido fixo para testes
VALID_UUID = "123e4567-e89b-12d3-a456-426655440000"

@pytest.fixture(autouse=True)
def _isolate_infrastructure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Substitui dependências externas por dublês de teste"""

    def _session_factory() -> DummySession:
        #Cria uma sessão desconectada do banco real
        return DummySession()

    _patch_task_attr(monkeypatch, "SessionLocal", _session_factory)
    #Evita tentativas de contato com Redis durante os testes
    _patch_task_attr(monkeypatch, "redis_client", None)
    _patch_task_attr(monkeypatch, "get_redis_client", lambda: None)


def _patch_task_attr(monkeypatch: pytest.MonkeyPatch, name: str, value) -> None:
    """Atualiza um atributo nos módulos de tasks real e de compatibilidade"""
    monkeypatch.setattr(f"market_alert.tasks.scraper_tasks.{name}", value, raising=False)
    monkeypatch.setattr(f"market_alert.tasks.collector_product_task.{name}", value, raising=False)

def test_collect_product_tasks_with_invalid_payload():
    """ Quando o payload é inválido (Pydantic), a task encerra sem exceção """
    result = collect_product_task.run(
        "url-invalida",
        VALID_UUID,
        "Nome Produto",
    )
    assert result is None

def test_collect_product_task_scraping_http_exception(monkeypatch):
    """ Simula falha HTTP ao chamar o serviço externo e verifica a exceção """

    def fake_service(*a, **k):
        raise ScraperClientError("erro", status_code=429)

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)

    with pytest.raises(ScraperError) as exc:
        collect_product_task.run(
            "https://mercadolivre.com.br/abc",
            VALID_UUID,
            "Produto A",
        )
    assert exc.value.status_code == 429

def test_scraper_error_is_picklable():
    """ Garante que o ScraperError pode ser serializado pelo Celery """
    err = ScraperError(status_code=400, detail="bad")
    dump = pickle.dumps(err)
    loaded = pickle.loads(dump)
    assert isinstance(loaded, ScraperError)
    assert loaded.status_code == 400
    assert loaded.detail == "bad"

def test_collect_product_task_generic_exception_creates_error(monkeypatch):
    """ Falhas genéricas na persistência devem gerar registro de erro """

    def fake_service(*a, **k):
        raise Exception("boom")

    captured = {}

    def fake_create(db, product_id, url, message, error_type):
        captured["args"] = (str(product_id), url, message, error_type)

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)
    _patch_task_attr(monkeypatch, "crud_errors.create_scraping_error", fake_create)

    collect_product_task.run(
        "https://ml.com/x",
        VALID_UUID,
        "Prod",
        VALID_UUID,
    )

    assert captured["args"][0] == VALID_UUID
    assert captured["args"][1] == "https://ml.com/x"


def test_collect_competitor_task_invalid_payload(monkeypatch):
    """ Quando o payload é invalido, a task apenas delega a coleta. """

    captured = {}

    def fake_apply_async(*_, **kwargs):
        captured.update(kwargs)
        return "delegated"

    collect_competitor_task.request = SimpleNamespace(delivery_info={})
    monkeypatch.setattr(collect_product_task, "apply_async", fake_apply_async)

    result = collect_competitor_task.apply(
        kwargs={"monitored_product_id": "not-a-uuid", "url": "https://mercadolivre.com.br/comp"}
    )

    assert result.get() == "delegated"
    assert captured["kwargs"]["payload"]["url"] == "https://mercadolivre.com.br/comp"
    assert captured["queue"] == "scraping"

def test_collect_competitor_task_preserva_headers(monkeypatch):
    """ Headers e fila são encaminhados para a task centralizada """

    captured = {}

    def fake_apply_async(*_, **kwargs):
        captured.update(kwargs)
        return "delegated"
    
    collect_competitor_task.request = SimpleNamespace(
        delivery_info={"routing_key": "scraping"}, headers={"x-request-id": "abc"}
    )
    monkeypatch.setattr(collect_product_task, "apply_async", fake_apply_async)

    result = collect_competitor_task.apply(
        kwargs={"payload": {"competitor_id": VALID_UUID, "url": "https://mercadolivre.com.br/comp"}}
    )
    
    assert result.get() == "delegated"
    assert captured["headers"] == {"x-request-id": "abc"}
    assert captured["queue"] == "scraping"

def test_collect_competitor_task_normaliza_usuario(monkeypatch):
    """owner_id legado deve ser propagado como user_id para a task alvo."""

    captured = {}

    def fake_apply_async(*_, **kwargs):
        captured.update(kwargs)
        return "delegated"

    collect_competitor_task.request = SimpleNamespace(delivery_info={})
    monkeypatch.setattr(collect_product_task, "apply_async", fake_apply_async)

    result = collect_competitor_task.apply(
        kwargs={"monitored_product_id": VALID_UUID, "url": "https://mercadolivre.com.br/abc", "owner_id": VALID_UUID}
    )

    assert result.get() == "delegated"
    assert captured["kwargs"]["payload"]["user_id"] == VALID_UUID


def test_collect_product_task_processa_sucesso(monkeypatch):
    """Resultado de sucesso não deve acionar retries."""

    def fake_service(*a, **k):
        return ScrapeResult(status="success", product_id=VALID_UUID, price_changed=True)

    captured = {}

    def fake_dispatch(monitored_id, **kwargs):
        captured["id"] = str(monitored_id)
        captured["kwargs"] = kwargs

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)
    _patch_task_attr(monkeypatch, "_dispatch_comparison_task", fake_dispatch)

    assert collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Produto",
        VALID_UUID,
    ) is None
    assert captured["id"] == VALID_UUID
    assert captured["kwargs"]["price_changed"] is True

def test_collect_product_task_availability_change(monkeypatch):
    """ Alterações de disponibilidade deve disparar comparação mesmo sem preço """
    def fake_service(*a, **k):
        return ScrapeResult(
            status="success",
            product_id=VALID_UUID,
            price_changed=False,
            availability_changed=True,
        )

    captured = {}

    def fake_dispatch(monitored_id, **kwargs):
        captured["id"] = str(monitored_id)
        captured["kwargs"] = kwargs

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)
    _patch_task_attr(monkeypatch, "_dispatch_comparison_task", fake_dispatch)

    assert collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Produto",
        VALID_UUID,
    ) is None
    assert captured["id"] == VALID_UUID
    assert captured["kwargs"]["availability_changed"] is True

def test_collect_product_task_no_result_dispara_retry(monkeypatch):
    """Cenário ``no_result`` deve solicitar reexecução posterior."""

    def fake_service(*a, **k):
        return ScrapeResult(status="no_result", product_id=VALID_UUID)

    captured = {}

    def fake_retry(*_, **kwargs):  # pragma: no cover - função auxiliar
        captured["countdown"] = kwargs.get("countdown")
        raise collect_product_task.MaxRetriesExceededError()

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)
    monkeypatch.setattr(collect_product_task, "retry", fake_retry)

    collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Produto",
    )

    assert captured["countdown"] is not None

def test_collect_product_task_no_result_registra_um_erro(monkeypatch):
    """Task de monitorado deve registrar um único erro por tentativa."""

    def fake_service(*a, **k):
        return ScrapeResult(status="no_result", product_id=VALID_UUID)

    calls = []

    def fake_retry(*_, **__):
        raise collect_product_task.MaxRetriesExceededError()

    def fake_create(db, product_id, url, message, error_type):
        calls.append((str(product_id), url, message, error_type))

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)
    _patch_task_attr(monkeypatch, "crud_errors.create_scraping_error", fake_create)
    monkeypatch.setattr(collect_product_task, "retry", fake_retry)

    collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Produto",
        VALID_UUID,
    )

    assert len(calls) == 1
    assert calls[0][0] == VALID_UUID


def test_collect_product_task_no_result_sem_id_nao_registra(monkeypatch):
    """Primeiro scraping sem ID deve apenas reagendar sem gravar erro."""

    def fake_service(*a, **k):
        return ScrapeResult(status="no_result", product_id=None)

    calls = []

    def fake_retry(*_, **__):
        raise collect_product_task.MaxRetriesExceededError()

    def fake_create(*_a, **_k):
        calls.append(True)

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)
    _patch_task_attr(monkeypatch, "crud_errors.create_scraping_error", fake_create)
    monkeypatch.setattr(collect_product_task, "retry", fake_retry)

    collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Produto",
    )

    assert calls == []

def test_collect_competitor_task_not_modified(monkeypatch):
    """Resposta 304 deve ainda manter o payload intacto ao delegar."""

    captured = {}

    def fake_apply_async(*_, **kwargs):
        captured.update(kwargs)
        return "delegated"

    collect_competitor_task.request = SimpleNamespace(delivery_info={})
    monkeypatch.setattr(collect_product_task, "apply_async", fake_apply_async)

    payload = {"competitor_id": VALID_UUID, "url": "https://mercadolivre.com.br/comp", "last_checked": None}
    result = collect_competitor_task.apply(kwargs={"payload": payload})

    assert result.get() == "delegated"
    assert captured["kwargs"]["payload"]["last_checked"] is None

def test_collect_competitor_task_availability_change(monkeypatch):
    """Delegação deve preencher monitored_id ausente quando informado via kwargs."""

    captured = {}

    def fake_apply_async(*_, **kwargs):
        captured.update(kwargs)
        return "delegated"

    collect_competitor_task.request = SimpleNamespace(delivery_info={"queue": "scraping"})
    monkeypatch.setattr(collect_product_task, "apply_async", fake_apply_async)

    result = collect_competitor_task.apply(
        kwargs={"monitored_product_id": VALID_UUID, "url": "https://mercadolivre.com.br/comp"}
    )

    assert result.get() == "delegated"
    assert captured["kwargs"]["payload"]["monitored_id"] == VALID_UUID
    assert captured["queue"] == "scraping"


def test_collect_competitor_task_respeita_routing_key(monkeypatch):
    """Fila de roteamento atual deve ser reaplicada na tarefa delegada."""

    captured = {}

    def fake_apply_async(*_, **kwargs):
        captured.update(kwargs)
        return "delegated"

    collect_competitor_task.request = SimpleNamespace(delivery_info={"routing_key": "custom"})
    monkeypatch.setattr(collect_product_task, "apply_async", fake_apply_async)

    result = collect_competitor_task.apply(
        kwargs={"payload": {"competitor_id": VALID_UUID, "url": "https://mercadolivre.com.br/comp"}}
    )

    assert result.get() == "delegated"
    assert captured["queue"] == "custom"


def test_collect_competitor_task_marca_kind(monkeypatch):
    """O payload final mantém o marcador de origem do concorrente."""

    captured = {}

    def fake_apply_async(*_, **kwargs):
        captured.update(kwargs)
        return "delegated"

    collect_competitor_task.request = SimpleNamespace(delivery_info={})
    monkeypatch.setattr(collect_product_task, "apply_async", fake_apply_async)

    result = collect_competitor_task.apply(
        kwargs={"monitored_product_id": VALID_UUID, "url": "https://mercadolivre.com.br/comp"}
    )

    assert result.get() == "delegated"
    assert captured["kwargs"]["payload"].get("kind") == "competitor"
    