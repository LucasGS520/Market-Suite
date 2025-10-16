""" Testes unitários para as etapas básicas do pipeline do scraper """

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from market_scraper.services.pipeline_steps import (
    FetchHTMLStep,
    GenericFallbackParserStep,
    HtmlMetadataParserStep,
    JsonLdParserStep,
    download_html,
)
from market_scraper.services.synergic_pipeline import PipelineContext
from market_scraper.core.config_scraper import settings
from market_scraper.utils import cache
from market_scraper.utils import singleflight
from shared.metrics.metrics_scraper import (
    SCRAPER_CLOUDSCRAPER_FALLBACK_TOTAL,
    SCRAPER_SINGLEFLIGHT_CALLS_TOTAL,
    SCRAPER_SINGLEFLIGHT_WAIT_SECONDS,
    SCRAPER_HTTP_RETRIES_TOTAL,
    SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
)


def _metric_value(metric: Any, sample_name: str, labels: dict[str, str]) -> float:
    """ Retorna o valor atual do sample de métrica solicitado """
    for collected in metric.collect():
        for sample in collected.samples:
            if sample.name == sample_name and all(
                sample.labels.get(key) == value for key, value in labels.items()
            ):
                return float(sample.value)
    return 0.0

class DummyAsyncClient:
    """ Cliente HTTP simplificado para controlar respostas nos testes """
    def __init__(self, responses: Iterator[httpx.Response]) -> None:
        self._responses = responses

    async def __aenter__(self) -> "DummyAsyncClient":
        return self
    
    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None
    
    async def get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        try:
            return next(self._responses)
        except StopIteration as exc:
            raise AssertionError("Respostas insuficientes para o teste") from exc

@pytest.mark.asyncio
async def test_download_html_utiliza_headers_compostos(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que headers básicos e Referer sejam construídos dinamicamente """

    url = "https://exemplo.com.br/produto"
    captured_headers: dict[str, str] = {}

    class CaptureClient:
        """ Cliente fake que captura headers enviados pelo FetchHTMLStep """

        async def __aenter__(self) -> "CaptureClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, request_url: str, headers: dict[str, str] | None = None) -> httpx.Response:
            assert request_url == url
            captured_headers.clear()
            if headers:
                captured_headers.update(headers)
            return httpx.Response(200, text="<html>ok</html>", request=httpx.Request("GET", url))

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.httpx.AsyncClient",
        lambda **__: CaptureClient(),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.ua_provider.get_user_agent",
        lambda *_args, **_kwargs: "UA-DE-TEXTO",
    )
    monkeypatch.setattr(
        settings,
        "SCRAPER_HEADERS_REFERER_TEMPLATE",
        "https://{domain}/origem",
    )

    html = await download_html(url, timeout=1.0)

    assert html == "<html>ok</html>"
    assert captured_headers["User-Agent"] == "UA-DE-TEXTO"
    assert captured_headers["Accept"] == settings.SCRAPER_HEADERS_ACCEPT
    assert captured_headers["Accept-Language"] == settings.SCRAPER_HEADERS_ACCEPT_LANGUAGE
    assert captured_headers["Connection"] == settings.SCRAPER_HEADERS_CONNECTION
    assert captured_headers["Referer"] == "https://exemplo.com.br/origem"

@pytest.mark.asyncio
async def test_download_html_registra_corpo_em_erro_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confirma logging sanitizado do corpo quando habilitado em settings """

    url = "https://bloqueado.com"
    response = httpx.Response(
        403,
        text="Checking your browser before accessing",
        request=httpx.Request("GET", url),
    )

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(iter([response])),
    )
    monkeypatch.setattr(settings, "SCRAPER_USE_CLOUDSCRAPER_FALLBACK", False)
    monkeypatch.setattr(settings, "SCRAPER_LOG_4XX_BODY", True)
    monkeypatch.setattr(settings, "SCRAPER_LOG_4XX_MAX_BYTES", 8)

    logs: list[dict[str, object]] = []

    def fake_warning(event: str, **kwargs: object) -> None:
        if event == "http_client_error":
            logs.append(kwargs)

    monkeypatch.setattr("market_scraper.services.pipeline_steps.logger.warning", fake_warning)

    with pytest.raises(httpx.HTTPStatusError):
        await download_html(url, timeout=1.0)

    assert logs, "Era esperado registro do erro 4xx"
    assert logs[0]["body_excerpt"] == "Checking"

@pytest.mark.asyncio
async def test_download_html_fallback_cloudscraper(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante fallback via cloudscraper quando sinais de Cloudflare aparecem """

    url = "https://protegido.com/produto"
    initial_response = httpx.Response(
        403,
        text="Attention Required! | Cloudflare",
        request=httpx.Request("GET", url),
    )

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(iter([initial_response])),
    )
    monkeypatch.setattr(settings, "SCRAPER_CLOUDSCRAPER_DOMAINS", ("protegido.com",))
    monkeypatch.setattr(settings, "SCRAPER_USE_CLOUDSCRAPER_FALLBACK", True)

    fallback_counter_before = _metric_value(
        SCRAPER_CLOUDSCRAPER_FALLBACK_TOTAL,
        "scraper_cloudscraper_fallback_total",
        {"domain": "protegido.com", "outcome": "success"},
    )

    calls = 0

    async def fake_execute(**_: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<html>fallback</html>", request=httpx.Request("GET", url))

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._execute_cloudscraper_request",
        fake_execute,
    )

    html = await download_html(url, timeout=1.0)

    assert html == "<html>fallback</html>"
    assert calls == 1

    fallback_counter_after = _metric_value(
        SCRAPER_CLOUDSCRAPER_FALLBACK_TOTAL,
        "scraper_cloudscraper_fallback_total",
        {"domain": "protegido.com", "outcome": "success"},
    )

    assert fallback_counter_after == pytest.approx(fallback_counter_before + 1)

@pytest.mark.asyncio
async def test_download_html_cloudscraper_respeita_http_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Confirma que o fallback reaproveita retries quando enfrenta erros 5xx """

    url = "https://retentativa.com/produto"
    initial_response = httpx.Response(
        403,
        text="Checking your browser before accessing",
        request=httpx.Request("GET", url),
    )

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(iter([initial_response])),
    )
    monkeypatch.setattr(settings, "SCRAPER_CLOUDSCRAPER_DOMAINS", ("retentativa.com",))
    monkeypatch.setattr(settings, "SCRAPER_USE_CLOUDSCRAPER_FALLBACK", True)

    fallback_counter_before = _metric_value(
        SCRAPER_CLOUDSCRAPER_FALLBACK_TOTAL,
        "scraper_cloudscraper_fallback_total",
        {"domain": "retentativa.com", "outcome": "success"},
    )
    retry_counter_before = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "cloudscraper", "reason": "server_error"},
    )

    responses = iter(
        [
            httpx.Response(503, request=httpx.Request("GET", url)),
            httpx.Response(
                200,
                text="<html>fallback-ok</html>",
                request=httpx.Request("GET", url),
            ),
        ]
    )

    calls = 0

    async def fake_execute(**_: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        try:
            return next(responses)
        except StopIteration as exc:
            raise AssertionError("Fallback chamado mais vezes que o esperado") from exc

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._execute_cloudscraper_request",
        fake_execute,
    )

    html = await download_html(url, timeout=1.0)

    assert html == "<html>fallback-ok</html>"
    assert calls == 2, "Retries deveriam repetir a chamada do fallback"

    fallback_counter_after = _metric_value(
        SCRAPER_CLOUDSCRAPER_FALLBACK_TOTAL,
        "scraper_cloudscraper_fallback_total",
        {"domain": "retentativa.com", "outcome": "success"},
    )
    retry_counter_after = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "cloudscraper", "reason": "server_error"},
    )

    assert fallback_counter_after == pytest.approx(fallback_counter_before + 1)
    assert retry_counter_after == pytest.approx(retry_counter_before + 1)

@pytest.mark.asyncio
async def test_download_html_retries_on_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confirma que respostas 429 respeitam Retry-After antes de nova tentativa """
    url = "https://exemple.com/produto"
    responses = iter(
        [
            httpx.Response(
                429,
                headers={"Retry-After": "0.2"},
                request=httpx.Request("GET", url),
            ),
            httpx.Response(200, text="<html>ok</html>", request=httpx.Request("GET", url)),
        ]
    )

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(responses),
    )

    counter_before = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "html", "reason": "too_many_requests"},
    )
    histogram_before = _metric_value(
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
        "scraper_http_retry_backoff_seconds_sum",
        {"target": "html", "reason": "too_many_requests"},
    )

    html = await download_html(url, timeout=1.0)

    assert html == "<html>ok</html>"

    counter_after = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "html", "reason": "too_many_requests"},
    )
    histogram_after = _metric_value(
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
        "scraper_http_retry_backoff_seconds_sum",
        {"target": "html", "reason": "too_many_requests"},
    )

    assert counter_after - counter_before == pytest.approx(1.0)
    assert pytest.approx(histogram_after - histogram_before, rel=0.2) == 0.2

@pytest.mark.asyncio
async def test_download_html_retries_on_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante backoff exponencial quando a origem responde com erro 5xx """
    url = "https://example.com/produto"
    monkeypatch.setattr(settings, "SCRAPER_HTTP_RETRY_BACKOFF_BASE", 0.05)
    responses = iter(
        [
            httpx.Response(502, request=httpx.Request("GET", url)),
            httpx.Response(200, text="<html>ok</html>", request=httpx.Request("GET", url)),
        ]
    )

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(responses),
    )

    counter_before = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "html", "reason": "server_error"},
    )
    histogram_before = _metric_value(
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
        "scraper_http_retry_backoff_seconds_sum",
        {"target": "html", "reason": "server_error"},
    )

    html = await download_html(url, timeout=1.0)

    assert html == "<html>ok</html>"

    counter_after = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "html", "reason": "server_error"},
    )
    histogram_after = _metric_value(
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
        "scraper_http_retry_backoff_seconds_sum",
        {"target": "html", "reason": "server_error"},
    )

    assert counter_after - counter_before == pytest.approx(1.0)
    assert pytest.approx(histogram_after - histogram_before, rel=0.2) == 0.05

@pytest.fixture
def context() -> PipelineContext:
    return PipelineContext(
        url="https://exemplo.com/produto",
        source="exemplo.com",
        default_step_timeout=0.5,
    )

@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """ Garante isolamento limpando o cache em memória entre os testes """
    cache.clear()

@pytest.mark.asyncio
async def test_fetch_html_reuses_existing_content(context) -> None:
    """ Quando o HTML já está no contexto a etapa deve evitar download """
    context.set_html("<html></html>")
    step = FetchHTMLStep()
    result = await step.run(context)
    assert result.status == "success"
    assert "já presente" in (result.message or "")

@pytest.mark.asyncio
async def test_fetch_html_respects_robots_block(
    monkeypatch: pytest.MonkeyPatch, context
) -> None:
    """ Valida que bloqueios definidos em robots.txt encerram a etapa imediatamente """

    async def unexpected_download(*_: object, **__: object) -> str:
        raise AssertionError("Download não deveria ser chamado quando robots bloqueia")

    async def fake_is_allowed(url: str, *, timeout: float | None = None) -> bool:
        assert timeout == context.default_step_timeout
        return False

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        unexpected_download,
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "unsupported_by_robots"
    assert context.html is None

@pytest.mark.asyncio
async def test_fetch_html_uses_cache_when_available(
    monkeypatch: pytest.MonkeyPatch, context
) -> None:
    """ Confirma que HTML em cache evita novo download e preserva métricas de hit """

    cache.set(context.url, "<html>cache</html>", ttl_seconds=60)

    async def unexpected_download(*_: object, **__: object) -> str:
        raise AssertionError("Download não deveria ocorrer em hit de cache")

    async def fake_is_allowed(url: str, *, timeout: float | None = None) -> bool:
        assert timeout == context.default_step_timeout
        return True

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        unexpected_download,
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_from_cache"
    assert context.html == "<html>cache</html>"

@pytest.mark.asyncio
async def test_fetch_html_downloads_and_caches_on_miss(
    monkeypatch: pytest.MonkeyPatch, context
) -> None:
    """ Garante download controlado e armazenamento do HTML quando cache falha """

    async def fake_download(url: str, *, timeout: float) -> str:
        assert timeout == context.default_step_timeout
        return "<html>novo</html>"

    async def fake_is_allowed(url: str, *, timeout: float | None = None) -> bool:
        assert timeout == context.default_step_timeout
        return True

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "HTML baixado com sucesso"
    assert context.html == "<html>novo</html>"
    assert cache.get(context.url) == "<html>novo</html>"

@pytest.mark.asyncio
async def test_fetch_html_timeout_when_robots_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Valida que o timeout configurado limita atrasos causados pela leitura de robots.txt """
    step_timeout = 0.2
    monkeypatch.setattr(settings, "SCRAPER_STEP_TIMEOUT_SECONDS", step_timeout)
    slow_context = PipelineContext(
        url="https://exemplo.com/produto",
        source="exemplo.com",
        default_step_timeout=step_timeout,
    )

    async def slow_is_allowed(url: str, *, timeout: float | None = None) -> bool:
        assert timeout == step_timeout
        await asyncio.sleep(step_timeout + 0.1)
        return True
    
    async def unexpected_download(*_: object, **__: object) -> str:
        raise AssertionError("Download não deve ocorrer após timeout de robots")

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        slow_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        unexpected_download,
    )

    step = FetchHTMLStep()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(step.run(slow_context), timeout=step_timeout)

@pytest.mark.asyncio
async def test_fetch_html_singleflight_avoids_duplicate_downloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Confere que apenas um download efetivo acontece quando múltiplos contextos usam a mesma URL """
    await singleflight.reset()
    cache.clear()

    for role in ("leader", "follower"):
        for outcome in ("success", "error"):
            SCRAPER_SINGLEFLIGHT_CALLS_TOTAL.labels(role=role, outcome=outcome)._value.set(0)
    follower_histogram = SCRAPER_SINGLEFLIGHT_WAIT_SECONDS.labels(role="follower")
    follower_histogram._sum.set(0.0)
    initial_count = next(
        sample.value for sample in follower_histogram._samples() if sample.name == "_count"
    )

    call_counter = 0

    async def fake_download(url: str, *, timeout: float) -> str:
        nonlocal call_counter
        call_counter += 1
        await asyncio.sleep(0.05)
        return "<html>novo</html>"
    
    async def always_allowed(url: str, *, timeout: float | None = None) -> bool:
        return True
    
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        always_allowed,
    )

    contexts = [
        PipelineContext(
            url="https://exemplo.com/produto",
            source="exemplo.com",
            default_step_timeout=1.0,
        )
        for _ in range(5)
    ]

    step = FetchHTMLStep()
    results = await asyncio.gather(*(step.run(ctx) for ctx in contexts))

    assert call_counter == 1
    assert all(result.status == "success" for result in results)
    assert all(ctx.html == "<html>novo</html>" for ctx in contexts)
    assert (
        SCRAPER_SINGLEFLIGHT_CALLS_TOTAL.labels(role="leader", outcome="success")._value.get() == 1
    )
    assert (
        SCRAPER_SINGLEFLIGHT_CALLS_TOTAL.labels(role="follower", outcome="success")._value.get() == 4
    )
    final_count = next(
        sample.value for sample in follower_histogram._samples() if sample.name == "_count"
    )
    assert final_count == initial_count + 4

@pytest.mark.asyncio
async def test_jsonld_parser_extracts_payload(context) -> None:
    """ Extrai dados a partir de JSON-LD disponível na página """
    context.set_html(
        """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Produto", "offers": {"price": "50"}}
        </script>
        </head></html>
        """
    )
    step = JsonLdParserStep()
    result = await step.run(context)
    assert result.status == "success"
    assert result.payload["name"] == "Produto"
    assert result.payload["current_price"] == "50.00"
    assert context.data["name"] == "Produto"
 
@pytest.mark.asyncio
async def test_generic_fallback_handles_missing_data(context) -> None:
    """ Confirma que a heurística retorna status vazio quando nada é encontrado """
    context.set_html("<html><body><p>sem preço</p></body></html>")
    step = GenericFallbackParserStep()
    result = await step.run(context)
    assert result.status == "empty"

@pytest.mark.asyncio
async def test_html_metadata_parser_uses_meta_tags(context) -> None:
    """ Verifica extração simples com meta tags e elementos básicos """
    context.set_html(
        """
        <html>
            <head><meta property="og:title" content="Produto" /></head>
            <body><span class="price">R$ 99,90</span></body>
        </html>
        """
    )
    step = HtmlMetadataParserStep()
    result = await step.run(context)
    assert result.status == "success"
    assert result.message == "Metadados HTML extraídos com sucesso"
    assert result.payload["name"] == "Produto"
    assert result.payload["current_price"] == "99.90"
    assert context.data["name"] == "Produto"
    assert context.data["current_price"] == "99.90"
    