from __future__ import annotations

import httpx

from market_scraper.parsers import parse_amazon_html, parse_magalu_html, parse_meli_html
from market_scraper.services.pipeline_steps import (
    AntiBotDetectionStep,
    DomainSpecificParserStep,
    FetchHTMLStep,
)
from market_scraper.services.synergic_pipeline import PipelineContext


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures mínimas de HTML para cada domínio
# ──────────────────────────────────────────────────────────────────────────────

_MELI_HTML_SUCCESS = (
    "<html><body>"
    "<h1 class='ui-pdp-title'>Notebook Lenovo IdeaPad</h1>"
    "<span class='andes-money-amount__fraction'>3.499</span>"
    "<span class='andes-money-amount__cents'>99</span>"
    "</body></html>"
)
_MELI_URL = "https://www.mercadolivre.com.br/produto/MLB123"

_AMAZON_HTML_SUCCESS = (
    "<html><body>"
    "<span id='productTitle'>Cafeteira Nespresso</span>"
    "<span id='price_inside_buybox'>R$ 299,00</span>"
    "</body></html>"
)
_AMAZON_URL = "https://www.amazon.com.br/dp/B0ABC12345"

_MAGALU_HTML_SUCCESS = (
    "<html><head>"
    "<meta property='og:title' content='Geladeira Brastemp Frost Free' />"
    "<meta itemprop='price' content='2599.0' />"
    "</head></html>"
)
_MAGALU_URL = "https://www.magazineluiza.com.br/produto/p/123456"

_HTML_NO_DATA = "<html><body><p>Produto não encontrado</p></body></html>"


async def test_fetch_html_step_returns_failure_when_robots_disallow(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        assert url == context.url
        assert timeout == 1.0
        return False

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "unsupported_by_robots"


async def test_fetch_html_step_reuses_cached_html(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.cache.get",
        lambda url: "<html>cached</html>",
    )

    async def fail_coalesce(key, producer):
        raise AssertionError("singleflight nao deveria ser usado com cache hit")

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        fail_coalesce,
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_from_cache"
    assert context.html == "<html>cached</html>"


async def test_fetch_html_step_infers_unavailability_from_http_status(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    request = httpx.Request("GET", context.url)
    response = httpx.Response(404, request=request)

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_coalesce(key, producer):
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    class _Inference:
        availability = False
        last_status = "not_found"
        confidence = "high"

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        fake_coalesce,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.infer_availability_from_http_status",
        lambda status_code, domain: _Inference(),
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.payload == {
        "name": None,
        "current_price": None,
        "url": context.url,
        "source": context.source,
        "availability": False,
        "last_status": "not_found",
    }
    assert context.html == ""
    assert context.data["http_status"] == 404
    assert context.data["availability"] is False
    assert context.data["last_status"] == "not_found"


async def test_domain_specific_parser_step_uses_dedicated_parser(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
        html="<html>ok</html>",
    )

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.get_domain_parser",
        lambda domain: ("example", lambda html, url: {"name": "Produto"}),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.run_parser_with_validation",
        lambda **kwargs: (
            True,
            {
                "name": "Produto",
                "current_price": "10.00",
                "url": context.url,
                "source": context.source,
            },
        ),
    )

    step = DomainSpecificParserStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.payload is not None
    assert context.data["domain_parser_suffix"] == "example"


async def test_domain_specific_parser_marks_no_domain_parser_when_unknown_domain():
    """DomainSpecificParserStep sinaliza no_domain_parser para domínios sem parser."""
    context = PipelineContext(
        url="https://unknown-store.com/product/1",
        source="unknown-store.com",
        default_step_timeout=1.0,
        html="<html><body>algum conteúdo</body></html>",
    )

    step = DomainSpecificParserStep()
    result = await step.run(context)

    assert result.status == "empty"
    assert context.data.get("no_domain_parser") is True


# ──────────────────────────────────────────────────────────────────────────────
# Fase 2 — testes de regressão: parsers por domínio (sucesso e no_result)
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_meli_html_extracts_name_and_price():
    result = parse_meli_html(_MELI_HTML_SUCCESS, _MELI_URL)
    assert result is not None
    assert result["name"] == "Notebook Lenovo IdeaPad"
    assert "3" in result["current_price"] and "499" in result["current_price"]
    assert result["url"] == _MELI_URL


def test_parse_meli_html_returns_none_when_no_extractable_data():
    result = parse_meli_html(_HTML_NO_DATA, _MELI_URL)
    assert result is None


def test_parse_amazon_html_extracts_name_and_price():
    result = parse_amazon_html(_AMAZON_HTML_SUCCESS, _AMAZON_URL)
    assert result is not None
    assert result["name"] == "Cafeteira Nespresso"
    assert "299" in result["current_price"]
    assert result["url"] == _AMAZON_URL


def test_parse_amazon_html_returns_none_when_no_extractable_data():
    result = parse_amazon_html(_HTML_NO_DATA, _AMAZON_URL)
    assert result is None


def test_parse_magalu_html_extracts_name_and_price():
    result = parse_magalu_html(_MAGALU_HTML_SUCCESS, _MAGALU_URL)
    assert result is not None
    assert result["name"] == "Geladeira Brastemp Frost Free"
    assert "2599" in result["current_price"] or "2.599" in result["current_price"]
    assert result["url"] == _MAGALU_URL


def test_parse_magalu_html_returns_none_when_no_extractable_data():
    result = parse_magalu_html(_HTML_NO_DATA, _MAGALU_URL)
    assert result is None


async def test_anti_bot_detection_step_returns_failure_on_cloudflare_pattern():
    """AntiBotDetectionStep detecta challenge Cloudflare e sinaliza contexto."""
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
        html="<html><body>challenges.cloudflare.com js challenge</body></html>",
    )
    step = AntiBotDetectionStep()
    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "anti_bot_page"
    assert context.data["anti_bot_detected"] is True
    assert context.data["anti_bot_pattern"] == "cloudflare_challenge"
    assert context.html == ""


async def test_anti_bot_detection_step_passes_clean_html():
    """AntiBotDetectionStep retorna empty (sem falha) quando HTML é limpo."""
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
        html="<html><body><h1>Produto Normal</h1></body></html>",
    )
    step = AntiBotDetectionStep()
    result = await step.run(context)

    assert result.status == "empty"
    assert context.data.get("anti_bot_detected") is None
