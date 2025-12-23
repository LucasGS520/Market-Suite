""" Testes unitários para as etapas básicas do pipeline do scraper """

from __future__ import annotations

import asyncio
import gzip
import io
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from types import ModuleType

import brotli
import httpx
import pytest

if "selectolax" not in sys.modules:
    _selectolax_module = ModuleType("selectolax")
    _selectolax_parser = ModuleType("selectolax.parser")
    setattr(_selectolax_parser, "HTMLParser", object)
    setattr(_selectolax_module, "parser", _selectolax_parser)
    sys.modules["selectolax"] = _selectolax_module
    sys.modules["selectolax.parser"] = _selectolax_parser

if "price_parser" not in sys.modules:
    _price_parser_module = ModuleType("price_parser")

    class _DummyPrice:
        """ Implementação mínima para emular interface de Price """

        def __init__(self, amount: Any | None = None) -> None:
            self.amount = amount

        @classmethod
        def fromstring(cls, raw: str) -> "_DummyPrice":
            #Retornamos instância sem valor para forçar fallback manual nos testes
            return cls(amount=None)

    setattr(_price_parser_module, "Price", _DummyPrice)
    sys.modules["price_parser"] = _price_parser_module

from market_scraper.services.pipeline_steps import (
    FetchHTMLStep,
    DomainSpecificParserStep,
    GenericFallbackParserStep,
    HtmlMetadataParserStep,
    JsonLdParserStep,
)
from market_scraper.services.parser_runner import run_parser_with_validation
from market_scraper.services.synergic_pipeline import PipelineContext
from market_scraper.core.config_scraper import settings
from market_scraper.utils.http_download import _log_client_error, download_html
from market_scraper.utils import cache
from market_scraper.utils import singleflight
from market_scraper.utils.http_retry import RetryableHTTPError
from market_scraper.utils.http_utils import ContentDecodeError
from shared.metrics.metrics_scraper import (
    SCRAPER_SINGLEFLIGHT_CALLS_TOTAL,
    SCRAPER_SINGLEFLIGHT_WAIT_SECONDS,
    SCRAPER_HTTP_RETRIES_TOTAL,
    SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
    SCRAPER_HTTP_DECODE_ERROR_TOTAL,
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

#Diretórios centralizado para carregar fixtures HTML reais das lojas suportados
_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"

class DummyAsyncClient:
    """ Cliente HTTP simplificado para controlar respostas nos testes """
    def __init__(self, responses: Iterator[httpx.Response], **_: object) -> None:
        self._responses = responses

    async def __aenter__(self) -> "DummyAsyncClient":
        return self
    
    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None
    
    async def get(
        self, 
        url: str, 
        headers: dict[str, str] | None = None,
        **__: object,
    ) -> httpx.Response:
        try:
            return next(self._responses)
        except StopIteration as exc:
            raise AssertionError("Respostas insuficientes para o teste") from exc

@pytest.mark.asyncio
async def test_download_html_utiliza_headers_compostos(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que headers básicos e Referer sejam construídos dinamicamente """

    url = "https://exemplo.com.br/produto"
    captured_headers: dict[str, str] = {}
    captured_cookies: dict[str, str] | None = None
    client_kwargs: dict[str, object] = {}

    class CaptureClient:
        """ Cliente fake que captura headers enviados pelo FetchHTMLStep """

        async def __aenter__(self) -> "CaptureClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(
            self, 
            request_url: str, 
            headers: dict[str, str] | None = None,
            cookies: dict[str, str] | None = None,
        ) -> httpx.Response:
            assert request_url == url
            captured_headers.clear()
            if headers:
                captured_headers.update(headers)
            nonlocal captured_cookies
            captured_cookies = cookies
            return httpx.Response(200, text="<html>ok</html>", request=httpx.Request("GET", url))
        
    def fake_async_client(**kwargs: object) -> CaptureClient:
        client_kwargs["last"] = kwargs
        return CaptureClient()

    monkeypatch.setattr(
        "market_scraper.utils.http_download.httpx.AsyncClient",
        fake_async_client,
    )
    monkeypatch.setattr(
        "market_scraper.utils.http_download.user_agents.get_user_agent",
        lambda *_args, **_kwargs: "UA-DE-TEXTO",
    )
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_ACCEPT", "text/html")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_ACCEPT_LANGUAGE", "pt-BR")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_CONNECTION", "keep-alive")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_CACHE_CONTROL", "max-age=0")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_ACCEPT_ENCODING", "gzip")
    monkeypatch.setattr(
        settings,
        "SCRAPER_HEADERS_REFERER_TEMPLATE",
        "https://{domain}/origem",
    )
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_ADDITIONAL", "Accept=custom/html||X-Test=valor")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_DEFAULT_COOKIES", "csrftoken=abc123")
    monkeypatch.setattr(settings, "SCRAPER_HTTP_FOLLOW_REDIRECTS", False)

    html = await download_html(url, timeout=1.0)

    assert html == "<html>ok</html>"
    assert captured_headers["User-Agent"] == "UA-DE-TEXTO"
    assert captured_headers["Accept"] == "custom/html"
    assert captured_headers["Accept-Language"] == settings.SCRAPER_HEADERS_ACCEPT_LANGUAGE
    assert captured_headers["Connection"] == settings.SCRAPER_HEADERS_CONNECTION
    assert captured_headers["Cache-Control"] == settings.SCRAPER_HEADERS_CACHE_CONTROL
    assert captured_headers["Accept-Encoding"] == settings.SCRAPER_HEADERS_ACCEPT_ENCODING
    assert captured_headers["Referer"] == "https://exemplo.com.br/origem"
    assert captured_headers["X-Test"] == "valor"
    assert captured_cookies == {"csrftoken": "abc123"}
    assert client_kwargs["last"]["follow_redirects"] is False

@pytest.mark.asyncio
async def test_download_html_respeita_timeout_por_dominio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante que timeouts específicos de domínio sejam considerados."""

    url = "https://exemplo.com.br/pagina"
    timeout_args: dict[str, float] = {}

    class DummyTimeout:
        """Captura parâmetros usados na criação do timeout personalizado."""

        def __init__(
            self,
            total: float,
            *,
            connect: float,
            read: float,
            write: float,
            pool: float,
        ) -> None:
            timeout_args.update(
                {
                    "total": total,
                    "connect": connect,
                    "read": read,
                    "write": write,
                    "pool": pool,
                }
            )

    monkeypatch.setattr(
        "market_scraper.utils.http_download.httpx.Timeout",
        DummyTimeout,
    )
    monkeypatch.setattr(
        "market_scraper.utils.http_download.httpx.AsyncClient",
        lambda **kwargs: DummyAsyncClient(
            iter([httpx.Response(200, text="<html>ok</html>", request=httpx.Request("GET", url))]),
            **kwargs,
        ),
    )
    monkeypatch.setattr(settings, "SCRAPER_HTTP_TIMEOUT_CONNECT", 3.0)
    monkeypatch.setattr(settings, "SCRAPER_HTTP_TIMEOUT_READ", 3.0)
    monkeypatch.setattr(settings, "SCRAPER_HTTP_TIMEOUT_WRITE", 3.0)
    monkeypatch.setattr(settings, "SCRAPER_HTTP_TIMEOUT_POOL", 2.5)
    monkeypatch.setattr(settings, "SCRAPER_HTTP_DOMAIN_TIMEOUTS", "exemplo.com.br=5.5")

    html = await download_html(url, timeout=1.0)

    assert html == "<html>ok</html>"
    assert timeout_args["total"] == 5.5
    assert timeout_args["connect"] == min(5.5, settings.SCRAPER_HTTP_TIMEOUT_CONNECT)
    assert timeout_args["read"] == min(5.5, settings.SCRAPER_HTTP_TIMEOUT_READ)
    assert timeout_args["write"] == min(5.5, settings.SCRAPER_HTTP_TIMEOUT_WRITE)
    assert timeout_args["pool"] == settings.SCRAPER_HTTP_TIMEOUT_POOL

@pytest.mark.asyncio
async def test_download_html_decodifica_brotli(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confere que o download trate respostas Brotli sem depender do httpx """
    url = "https://brotli.com/produto"
    original = "<html>brotli</html>"
    response = httpx.Response(
        200,
        content=brotli.compress(original.encode("utf-8")),
        headers={"Content-Encoding": "br"},
        request=httpx.Request("GET", url),
    )

    monkeypatch.setattr(
        "market_scraper.utils.http_download.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(iter([response])),
    )

    html = await download_html(url, timeout=1.0)

    assert html == original

@pytest.mark.asyncio
async def test_download_html_decodifica_gzip(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Valida suporte a gzip quando httpx retorna bytes comprimidos """
    url = "https://gzip.com/item"
    original = "<html>gzip</html>"
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz_file:
        gz_file.write(original.encode("utf-8"))
    response = httpx.Response(
        200,
        content=buffer.getvalue(),
        headers={"Content-Encoding": "gzip"},
        request=httpx.Request("GET", url),
    )

    monkeypatch.setattr(
        "market_scraper.utils.http_download.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(iter([response])),
    )

    html = await download_html(url, timeout=1.0)

    assert html == original

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
        "market_scraper.utils.http_download.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(iter([response])),
    )
    monkeypatch.setattr(settings, "SCRAPER_LOG_4XX_BODY", True)
    monkeypatch.setattr(settings, "SCRAPER_LOG_4XX_MAX_BYTES", 8)

    logs: list[dict[str, object]] = []

    def fake_warning(event: str, **kwargs: object) -> None:
        if event == "http_client_error":
            logs.append(kwargs)

    monkeypatch.setattr("market_scraper.utils.http_download.logger.warning", fake_warning)

    with pytest.raises(httpx.HTTPStatusError):
        await download_html(url, timeout=1.0)

    assert logs, "Era esperado registro do erro 4xx"
    assert logs[0]["body_excerpt"] == "Checking"

@pytest.mark.asyncio
async def test_download_html_registra_headers_em_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confirma que o download registra cabeçalhos relevantes em nível debug """

    url = "https://diagnostico.com/pagina"
    response = httpx.Response(
        200,
        headers={"Content-Type": "text/html", "Content-Encoding": "identity"},
        text="<html></html>",
        request=httpx.Request("GET", url),
    )

    monkeypatch.setattr(
        "market_scraper.utils.http_download.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(iter([response])),
    )

    debug_logs: list[dict[str, object]] = []

    def fake_debug(event: str, **kwargs: object) -> None:
        if event == "http_download_metadata":
            debug_logs.append(kwargs)

    monkeypatch.setattr("market_scraper.utils.http_download.logger.debug", fake_debug)

    html = await download_html(url, timeout=1.0)

    assert html == "<html></html>"
    assert debug_logs, "Era esperado log em nível debug"

@pytest.mark.asyncio
async def test_download_html_registra_metricas_em_erro_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Checa incremento de métricas e log quando a decodificação falha """
    url = "https://erro.decode"
    response = httpx.Response(
        200,
        content=b"\x00\x01",
        headers={"Content-Encoding": "br"},
        request=httpx.Request("GET", url),
    )

    monkeypatch.setattr(
        "market_scraper.utils.http_download.httpx.AsyncClient",
        lambda **__: DummyAsyncClient(iter([response])),
    )

    def fake_decode(_: httpx.Response) -> str:
        raise ContentDecodeError(encoding="br", reason="decode_failed")
    
    monkeypatch.setattr(
        "market_scraper.utils.http_download.decode_http_body",
        fake_decode,
    )

    before = _metric_value(
        SCRAPER_HTTP_DECODE_ERROR_TOTAL,
        "scraper_http_decode_error_total",
        {"domain": "erro.decode", "encoding": "br", "reason": "decode_failed"},
    )

    with pytest.raises(ValueError):
        await download_html(url, timeout=1.0)

    after = _metric_value(
        SCRAPER_HTTP_DECODE_ERROR_TOTAL,
        "scraper_http_decode_error_total",
        {"domain": "erro.decode", "encoding": "br", "reason": "decode_failed"},
    )
    assert after == before + 1

@pytest.mark.asyncio
async def test_download_html_repropaga_http_status_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante preservação do request/response ao repropagar erros transitórios """
    url = "https://erro-temporario.com/recurso"
    request = httpx.Request("GET", url)
    response = httpx.Response(503, request=request)
    status_error = httpx.HTTPStatusError("erro", request=request, response=response)

    async def fake_operation() -> httpx.Response:
        raise RetryableHTTPError(target="html", reason="server_error", status_code=503) from status_error

    monkeypatch.setattr(
        "market_scraper.utils.http_download.build_retrying_operation",
        lambda *, target, operation: fake_operation,
    )
    monkeypatch.setattr(
        "market_scraper.utils.http_download.user_agents.get_user_agent",
        lambda *_a, **_k: "UA-DE-TESTE",
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await download_html(url, timeout=1.0)

    assert exc_info.value.request is request
    assert exc_info.value.response is response

def test_run_parser_with_validation_registra_rejeicao() -> None:
    """ Confirma que rejeições do validador fiquem disponíveis no contexto """
    context = PipelineContext(
        url="https://exemplo.com/produto",
        source="exemplo.com",
        default_step_timeout=1.0,
    )
    context.set_html("<html></html>")

    def _fake_parser(_: str, __: str) -> dict[str, str]:
        return {"name": "", "current_price": "10"}
    
    ok, payload = run_parser_with_validation(
        parser=_fake_parser,
        context=context,
        step_name="json_ld_parser",
    )

    assert not ok
    assert payload is None
    failures = context.data.get("validation_failures")
    assert failures and failures[0]["reason_code"] == "name_missing"

@pytest.mark.asyncio
async def test_domain_specific_parser_aplica_parser_de_mercadolivre() -> None:
    """Garante que o parser dedicado trate HTML estático do Mercado Livre"""

    html_path = _FIXTURES_DIR / "mercadolivre" / "product_static.html"
    html = html_path.read_text(encoding="utf-8")
    context = PipelineContext(
        url="https://produto.mercadolivre.com.br/MLB-123456789",
        source="produto.mercadolivre.com.br",
        default_step_timeout=1.0,
    )
    context.set_html(html)

    step = DomainSpecificParserStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.payload == {
        "name": "Console Retro Game",
        "current_price": "549.90",
        "url": "https://produto.mercadolivre.com.br/MLB-123456789",
        "source": "produto.mercadolivre.com.br",
        "currency": None,
        "availability": None,
        "last_status": None,
    }
    assert context.data.get("domain_parser_suffix") == "mercadolivre.com.br"


@pytest.mark.asyncio
async def test_domain_specific_parser_ignora_dominios_nao_mapreados() -> None:
    """Confirma que a etapa retorna vazio quando não há parser dedicado"""

    context = PipelineContext(
        url="https://loja.exemplo.com/item",
        source="loja.exemplo.com",
        default_step_timeout=1.0,
    )
    context.set_html("<html><body><h1>Produto</h1></body></html>")

    step = DomainSpecificParserStep()
    result = await step.run(context)

    assert result.status == "empty"
    assert result.message == "Domínio sem parser dedicado"

def test_log_client_error_trunca_e_decodifica_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante truncamento em bytes e decodificações tolerante ao registrar 4xx """

    url = "https://exemplo.com/recurso"
    response = httpx.Response(
        403,
        content=b"A" * 9 + b"\xffresto",
        request=httpx.Request("GET", url),
    )
    monkeypatch.setattr(settings, "SCRAPER_LOG_4XX_BODY", True)
    monkeypatch.setattr(settings, "SCRAPER_LOG_4XX_MAX_BYTES", 10)

    logs: list[dict[str, object]] = []

    def fake_warning(event: str, **kwargs: object) -> None:
        if event == "http_client_error":
            logs.append(kwargs)

    monkeypatch.setattr("market_scraper.utils.http_download.logger.warning", fake_warning)

    _log_client_error(response=response, url=url, domain="exemplo.com", user_agent="teste")

    assert logs, "Era esperado registro do erro 4xx"
    assert logs[0]["body_excerpt"] == "AAAAAAAAA�"

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
        "market_scraper.utils.http_download.httpx.AsyncClient",
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
        "market_scraper.utils.http_download.httpx.AsyncClient",
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
    