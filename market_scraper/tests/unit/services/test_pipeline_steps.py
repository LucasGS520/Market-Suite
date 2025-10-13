""" Testes unitários para as etapas básicas do pipeline do scraper """

from __future__ import annotations

import asyncio

import pytest

from market_scraper.services.pipeline_steps import (
    FetchHTMLStep,
    GenericFallbackParserStep,
    HtmlMetadataParserStep,
    JsonLdParserStep,
)
from market_scraper.services.synergic_pipeline import PipelineContext
from market_scraper.core.config_scraper import settings
from market_scraper.utils import cache
from market_scraper.utils import singleflight
from shared.metrics.metrics_scraper import (
    SCRAPER_SINGLEFLIGHT_CALLS_TOTAL,
    SCRAPER_SINGLEFLIGHT_WAIT_SECONDS,
)


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

    monkeypatch.setattr(settings, "SCRAPER_CACHE_ENABLED", False)
    monkeypatch.setattr(settings, "SCRAPER_SINGLEFLIGHT_ENABLED", True)

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
    