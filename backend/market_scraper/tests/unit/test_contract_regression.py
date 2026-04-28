"""Golden tests de regressão de contrato — POST /scraper/parse

Cobre invariantes do contrato público congelado (CONTRATO_HTTP_SCRAPER.md):
- Todos os status HTTP mapeados aos cenários corretos.
- X-MarketScraper-Contract-Version: v1 em TODAS as respostas.
- ErrorResponse sempre contém message + error_code + trace_id.
- trace_id propagado de metadata para ErrorResponse.
- Cenários não cobertos pelos demais testes de rota/fluxo.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from shared.schemas.shared_schemas_scraper import (
    SCRAPER_CONTRACT_VERSION,
    SCRAPER_CONTRACT_VERSION_HEADER,
    ParserResponse,
)
from shared.utils.url_validation import UrlIssue

from market_scraper.main import app
from market_scraper.scraper_orchestrator.parse_product import (
    ParseProductError,
    ParseProductNoResult,
    ParseProductSuccess,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _client() -> TestClient:
    return TestClient(app)


def _stub_prereqs(monkeypatch) -> None:
    """Stub de pré-condições comuns: normalização, compatibilidade e cache miss."""
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: None,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.get_cached_response",
        lambda url: None,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.invalidate_cached_response",
        lambda url: None,
    )


def _stub_use_case_error(monkeypatch, *, error_code: str, message: str, http_status: int) -> None:
    """Stub do use case retornando ParseProductError com código canônico."""
    result = ParseProductError(
        kind="error",
        issue=UrlIssue(code=error_code, message=message),
        http_status=http_status,
        stage_timings={},
    )

    async def fake_execute(self, *args, **kwargs):
        return result

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.ParseProduct.execute",
        fake_execute,
    )


def _stub_use_case_error_with_invalidate(
    monkeypatch, *, error_code: str, message: str, http_status: int
) -> None:
    """Stub do use case retornando ParseProductError com invalidate_cache=True."""
    result = ParseProductError(
        kind="error",
        issue=UrlIssue(code=error_code, message=message),
        http_status=http_status,
        stage_timings={},
        invalidate_cache=True,
    )

    async def fake_execute(self, *args, **kwargs):
        return result

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.ParseProduct.execute",
        fake_execute,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Invariante: X-MarketScraper-Contract-Version presente em todas as respostas
# ──────────────────────────────────────────────────────────────────────────────

def test_contract_version_header_present_on_400(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: UrlIssue(
            code="blocked_host", message="Host bloqueado"
        ),
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 400
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION


def test_contract_version_header_present_on_422(monkeypatch):
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="too_many_redirects",
        message="A URL entrou em loop de redirecionamento",
        http_status=422,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 422
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION


def test_contract_version_header_present_on_429(monkeypatch):
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="anti_bot_page",
        message="Página de proteção anti-bot detectada",
        http_status=429,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 429
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION


def test_contract_version_header_present_on_503(monkeypatch):
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="pipeline_degraded",
        message="Serviço temporariamente degradado",
        http_status=503,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 503
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION


def test_contract_version_header_present_on_504(monkeypatch):
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="playwright_timeout",
        message="Tempo limite excedido ao renderizar a página com browser",
        http_status=504,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 504
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION


# ──────────────────────────────────────────────────────────────────────────────
# Invariante: ErrorResponse contém message + error_code + trace_id
# ──────────────────────────────────────────────────────────────────────────────

def _assert_error_schema(body: dict) -> None:
    assert "message" in body, "ErrorResponse deve conter 'message'"
    assert "error_code" in body, "ErrorResponse deve conter 'error_code'"
    assert "trace_id" in body, "ErrorResponse deve conter 'trace_id'"
    assert body["message"], "'message' não pode ser vazio"
    assert body["error_code"], "'error_code' não pode ser vazio"


def test_error_response_schema_on_400(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: UrlIssue(
            code="blocked_host", message="Host bloqueado"
        ),
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 400
    _assert_error_schema(response.json())


def test_error_response_schema_on_403(monkeypatch):
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="robots_disallowed",
        message="O acesso à URL foi bloqueado pelas regras de robots.txt",
        http_status=403,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 403
    _assert_error_schema(response.json())


def test_error_response_schema_on_422_no_result(monkeypatch):
    _stub_prereqs(monkeypatch)
    result = ParseProductNoResult(kind="no_result", reason_code="extraction_empty", stage_timings={})

    async def fake_execute(self, *args, **kwargs):
        return result

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.ParseProduct.execute",
        fake_execute,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 422
    body = response.json()
    _assert_error_schema(body)
    assert body["error_code"] == "no_result"


def test_error_response_schema_on_504(monkeypatch):
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="playwright_timeout",
        message="Tempo limite excedido ao renderizar a página com browser",
        http_status=504,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 504
    _assert_error_schema(response.json())


# ──────────────────────────────────────────────────────────────────────────────
# Invariante: trace_id propagado do metadata para ErrorResponse
# ──────────────────────────────────────────────────────────────────────────────

def test_trace_id_propagated_from_metadata_to_error_response(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: UrlIssue(
            code="blocked_host", message="Host bloqueado"
        ),
    )

    response = _client().post(
        "/scraper/parse",
        json={
            "url": "example.com/product",
            "metadata": {"trace_id": "trace-from-caller-abc"},
        },
    )

    assert response.status_code == 400
    assert response.json()["trace_id"] == "trace-from-caller-abc"


def test_trace_id_generated_when_absent_from_metadata(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: UrlIssue(
            code="blocked_host", message="Host bloqueado"
        ),
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 400
    trace_id = response.json().get("trace_id")
    assert trace_id is not None
    assert len(trace_id) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Cenários de erro por código canônico
# ──────────────────────────────────────────────────────────────────────────────

def test_503_when_playwright_not_ready(monkeypatch):
    """503 quando fallback browser não está disponível (playwright_not_ready → pipeline_degraded)."""
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="pipeline_degraded",
        message="Serviço temporariamente degradado; fallback de browser indisponível",
        http_status=503,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "pipeline_degraded"


def test_503_when_pipeline_degraded(monkeypatch):
    """503 quando pipeline sinaliza degradação geral (pipeline_degraded)."""
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="pipeline_degraded",
        message="Serviço temporariamente degradado; fallback de browser indisponível",
        http_status=503,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "pipeline_degraded"


def test_503_when_playwright_fetch_error(monkeypatch):
    """503 quando browser falha ao buscar conteúdo (playwright_fetch_error)."""
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="playwright_fetch_error",
        message="Erro ao obter conteúdo via browser; tente novamente",
        http_status=503,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "playwright_fetch_error"


def test_504_when_playwright_timeout(monkeypatch):
    """504 quando browser excede timeout de renderização (playwright_timeout)."""
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="playwright_timeout",
        message="Tempo limite excedido ao renderizar a página com browser",
        http_status=504,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 504
    assert response.json()["error_code"] == "playwright_timeout"


def test_429_when_rate_limiter_cooldown(monkeypatch):
    """429 quando domínio está em cooldown pelo rate limiter."""
    _stub_prereqs(monkeypatch)
    _stub_use_case_error_with_invalidate(
        monkeypatch,
        error_code="rate_limiter_cooldown",
        message="Limite de requisições atingido para este domínio; tente novamente em instantes",
        http_status=429,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 429
    assert response.json()["error_code"] == "rate_limiter_cooldown"


# ──────────────────────────────────────────────────────────────────────────────
# Invariante: X-MarketScraper-Cache-Status presente em respostas 200
# ──────────────────────────────────────────────────────────────────────────────

def test_cache_status_header_present_on_200(monkeypatch):
    """X-MarketScraper-Cache-Status deve estar presente em respostas 200."""
    _stub_prereqs(monkeypatch)

    parser_response = ParserResponse(
        name="Produto Teste",
        availability=True,
        url="https://example.com/product",
        source="example.com",
    )
    result = ParseProductSuccess(kind="success", parser_response=parser_response, stage_timings={})

    async def fake_execute(self, *args, **kwargs):
        return result

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.ParseProduct.execute",
        fake_execute,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.store_response",
        lambda url, response: None,
    )

    response = _client().post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 200
    assert "x-marketscraper-cache-status" in response.headers
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION
