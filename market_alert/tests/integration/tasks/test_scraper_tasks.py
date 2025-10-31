""" Testes de integração isolados para as tasks de scraping """

import pickle
from types import SimpleNamespace

import pytest

from shared.schemas.schemas_scraper import ScrapeResult
from shared.exceptions import ScraperError
from market_alert.scraper.scraper_client import ScraperClientError
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

def test_collect_product_tasks_with_invalid_payload():
    """ Quando o payload é inválido (Pydantic), a task encerra sem exceção """
    result = collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Nome Produto",
        "not-a-decimal",
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
            99.0,
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
        99.0,
        VALID_UUID,
    )

    assert captured["args"][0] == VALID_UUID
    assert captured["args"][1] == "https://ml.com/x"


def test_collect_competitor_task_invalid_payload():
    """ Quando o payload é invalido, a task deve encerrar sem exceção """
    result = collect_competitor_task.run(
        "not-a-uuid",
        "https://mercadolivre.com.br/comp",
    )
    assert result is None

def test_collect_competitor_task_scraping_http_exception(monkeypatch):
    """ Erro HTTP no serviço externo deve ser propagado como ScraperError """

    def fake_service(*a, **k):
        raise ScraperClientError("erro", status_code=500)
    
    def fake_retry(*_, **kwargs):
        raise RuntimeError(f"retry:{kwargs.get('countdown')}")

    _patch_task_attr(monkeypatch, "scrape_competitor_product", fake_service)
    _patch_task_attr(monkeypatch, "get_monitored_product_by_id", lambda db, pid: SimpleNamespace(user_id=VALID_UUID))
    monkeypatch.setattr(collect_competitor_task, "retry", fake_retry)

    with pytest.raises(RuntimeError) as exc:
        collect_competitor_task.run(
            VALID_UUID,
            "https://mercadolivre.com.br/comp",
        )
    assert "retry" in str(exc.value)

def test_collect_competitor_task_http_5xx_retorna_retry(monkeypatch):
    """Erro 5xx deve acionar retry progressivo."""

    def fake_service(*a, **k):
        raise ScraperClientError("erro", status_code=500)

    def fake_retry(*_, **kwargs):
        raise RuntimeError(f"retry:{kwargs.get('countdown')}")

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)
    monkeypatch.setattr(collect_product_task, "retry", fake_retry)
    _patch_task_attr(monkeypatch, "crud_errors.create_scraping_error", lambda *a, **k: None)

    with pytest.raises(RuntimeError) as exc:
        collect_product_task.run(
            "https://mercadolivre.com.br/abc",
            VALID_UUID,
            "Produto",
            10.0,
        )

    assert "retry" in str(exc.value)


def test_collect_product_task_processa_sucesso(monkeypatch):
    """Resultado de sucesso não deve acionar retries."""

    def fake_service(*a, **k):
        return ScrapeResult(status="success", product_id=VALID_UUID, price_changed=True)

    _patch_task_attr(monkeypatch, "scrape_monitored_product", fake_service)

    assert collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Produto",
        10.0,
        VALID_UUID,
    ) is None


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
        10.0,
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
        10.0,
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
        10.0,
    )

    assert calls == []

def test_collect_competitor_task_not_modified(monkeypatch):
    """Resposta 304 deve evitar reprocessamento de comparação."""

    captured = {}

    def fake_service(*a, **k):
        return ScrapeResult(status="not_modified", product_id=VALID_UUID, price_changed=False)

    def fake_compare(arg):
        captured["called"] = True

    _patch_task_attr(monkeypatch, "scrape_competitor_product", fake_service)
    _patch_task_attr(monkeypatch, "get_monitored_product_by_id", lambda db, pid: SimpleNamespace(user_id=VALID_UUID))
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.compare_prices_task", SimpleNamespace(delay=fake_compare))

    assert collect_competitor_task.run(VALID_UUID, "https://mercadolivre.com.br/comp") is None
    assert "called" not in captured

def test_collect_competitor_task_no_result_dispara_retry(monkeypatch):
    """Resposta ``no_result`` deve reagendar nova tentativa."""

    def fake_service(*a, **k):
        return ScrapeResult(status="no_result", product_id=VALID_UUID)

    captured = {}

    def fake_retry(*_, **kwargs):
        captured["countdown"] = kwargs.get("countdown")
        raise collect_competitor_task.MaxRetriesExceededError()

    _patch_task_attr(monkeypatch, "scrape_competitor_product", fake_service)
    _patch_task_attr(monkeypatch, "crud_errors.create_scraping_error", lambda *a, **k: None)
    _patch_task_attr(monkeypatch, "get_monitored_product_by_id", lambda db, pid: SimpleNamespace(user_id=VALID_UUID))
    monkeypatch.setattr(collect_competitor_task, "retry", fake_retry)

    collect_competitor_task.run(
        VALID_UUID,
        "https://mercadolivre.com.br/comp",
    )

    assert captured["countdown"] is not None


def test_collect_competitor_task_no_result_registra_um_erro(monkeypatch):
    """Task de concorrente registra apenas um erro por execução."""

    def fake_service(*a, **k):
        return ScrapeResult(status="no_result", product_id=VALID_UUID)

    calls = []

    def fake_retry(*_, **__):
        raise collect_competitor_task.MaxRetriesExceededError()

    def fake_create(db, product_id, url, message, error_type):
        calls.append((str(product_id), url, message, error_type))

    _patch_task_attr(monkeypatch, "scrape_competitor_product", fake_service)
    _patch_task_attr(monkeypatch, "crud_errors.create_scraping_error", fake_create)
    _patch_task_attr(monkeypatch, "get_monitored_product_by_id", lambda db, pid: SimpleNamespace(user_id=VALID_UUID))
    monkeypatch.setattr(collect_competitor_task, "retry", fake_retry)

    collect_competitor_task.run(
        VALID_UUID,
        "https://mercadolivre.com.br/comp",
    )

    assert len(calls) == 1
    assert calls[0][0] == VALID_UUID
    