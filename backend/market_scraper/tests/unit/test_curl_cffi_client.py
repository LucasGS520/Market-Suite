"""Testes unitários para CurlffiHTTPClient (Camada 1 — curl_cffi).

Como ``curl_cffi`` pode não estar instalado no ambiente de CI, todos os
testes injetam um módulo falso via ``patch.dict(sys.modules)`` antes de
importar o cliente. Isso isola completamente a lógica testada da biblioteca
real e garante que os testes rodem sem dependência de rede.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from market_scraper.utils.http_download import CurlffiHTTPClient, CurlcffiErrorType


# ─────────────────────────────────────────────────────────────────────────────
# Infra de fake curl_cffi
# ─────────────────────────────────────────────────────────────────────────────

class _FakeCurlRequestsError(Exception):
    """Substituto de ``curl_cffi.requests.RequestsError`` com atributo ``code``."""

    def __init__(self, message: str, *, code: int) -> None:
        super().__init__(message)
        self.code = code


class _FakeResponse:
    """Substituto de resposta curl_cffi para testes."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: str = "<html>" + "x" * (6 * 1024) + "</html>",
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.status_code = status_code
        self.text = body
        self.content = body.encode("utf-8")
        self.headers: dict[str, str] = {"Content-Type": content_type}
        self.encoding = "utf-8"


def _fake_curl_module(*, response: _FakeResponse | None = None, side_effect: Exception | None = None) -> MagicMock:
    """Cria um módulo ``curl_cffi.requests`` falso.

    Ou retorna *response* no ``.get()``, ou levanta *side_effect*.
    Expõe ``RequestsError = _FakeCurlRequestsError`` para que
    ``except RequestsError`` no cliente funcione corretamente.
    """
    session_mock = MagicMock()

    if side_effect is not None:
        session_mock.get = AsyncMock(side_effect=side_effect)
    else:
        session_mock.get = AsyncMock(return_value=response)

    @asynccontextmanager
    async def _session_ctx(*args, **kwargs) -> AsyncGenerator:
        yield session_mock

    mod = MagicMock()
    mod.AsyncSession = _session_ctx
    mod.RequestsError = _FakeCurlRequestsError
    return mod


def _inject_curl_module(mod: MagicMock):
    """Context manager que injeta módulo falso no sys.modules."""
    return patch.dict(sys.modules, {"curl_cffi": MagicMock(), "curl_cffi.requests": mod})


# Resposta grande padrão (6 KB — acima do mínimo)
_BIG_BODY = "<html>" + "x" * (6 * 1024) + "</html>"
_URL = "https://www.mercadolivre.com.br/p/MLB123"


# ─────────────────────────────────────────────────────────────────────────────
# Testes de sucesso
# ─────────────────────────────────────────────────────────────────────────────

async def test_curl_cffi_client_fetch_success():
    """Retorna HTML quando o servidor responde 200 com corpo ≥ 5 KB."""
    fake_mod = _fake_curl_module(response=_FakeResponse(status_code=200, body=_BIG_BODY))
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        html = await client.fetch_html(_URL, timeout=5.0)

    assert html == _BIG_BODY


async def test_curl_cffi_client_fetch_returns_small_html():
    """Corpo abaixo de 5 KB é retornado normalmente (classificação de tamanho é
    responsabilidade do ResponseClassifier na Fase 3, não do cliente HTTP)."""
    small_body = "<html>ok</html>"
    fake_mod = _fake_curl_module(response=_FakeResponse(status_code=200, body=small_body))
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        html = await client.fetch_html(_URL, timeout=5.0)

    assert html == small_body


# ─────────────────────────────────────────────────────────────────────────────
# Testes de composição de headers
# ─────────────────────────────────────────────────────────────────────────────

async def test_curl_cffi_client_headers_contain_user_agent_and_pt_br():
    """Headers enviados incluem User-Agent Chrome e Accept-Language pt-BR."""
    captured: dict = {}

    async def fake_get(url, *, headers, **kwargs):
        captured["headers"] = headers
        return _FakeResponse()

    session_mock = MagicMock()
    session_mock.get = fake_get

    @asynccontextmanager
    async def fake_ctx(*args, **kwargs):
        yield session_mock

    fake_mod = MagicMock()
    fake_mod.AsyncSession = fake_ctx
    fake_mod.RequestsError = _FakeCurlRequestsError

    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        await client.fetch_html(_URL, timeout=5.0)

    assert "User-Agent" in captured["headers"]
    ua = captured["headers"]["User-Agent"]
    assert "Chrome" in ua or "Mozilla" in ua

    accept_lang = captured["headers"].get("Accept-Language", "")
    assert "pt-BR" in accept_lang or "pt" in accept_lang


# ─────────────────────────────────────────────────────────────────────────────
# Testes de mapeamento de erros — curl_cffi → httpx
# ─────────────────────────────────────────────────────────────────────────────

async def test_curl_cffi_client_timeout_raises_httpx_read_timeout():
    """Timeout do curl (code=28) → httpx.ReadTimeout."""
    curl_exc = _FakeCurlRequestsError("Operation timed out", code=28)
    fake_mod = _fake_curl_module(side_effect=curl_exc)
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.ReadTimeout):
            await client.fetch_html(_URL, timeout=5.0)


async def test_curl_cffi_client_connect_error_raises_httpx_connect_error():
    """Falha de conexão (code=7) → httpx.ConnectError."""
    curl_exc = _FakeCurlRequestsError("Connection refused", code=7)
    fake_mod = _fake_curl_module(side_effect=curl_exc)
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.ConnectError):
            await client.fetch_html(_URL, timeout=5.0)


async def test_curl_cffi_client_too_many_redirects_raises_httpx():
    """Redirecionamentos em excesso (code=47) → httpx.TooManyRedirects."""
    curl_exc = _FakeCurlRequestsError("Maximum redirects followed", code=47)
    fake_mod = _fake_curl_module(side_effect=curl_exc)
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.TooManyRedirects):
            await client.fetch_html(_URL, timeout=5.0)


async def test_curl_cffi_client_invalid_url_raises_httpx():
    """URL malformada (code=3) → httpx.InvalidURL."""
    curl_exc = _FakeCurlRequestsError("URL malformat", code=3)
    fake_mod = _fake_curl_module(side_effect=curl_exc)
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.InvalidURL):
            await client.fetch_html(_URL, timeout=5.0)


async def test_curl_cffi_client_unsupported_protocol_raises_httpx():
    """Protocolo não suportado (code=1) → httpx.UnsupportedProtocol."""
    curl_exc = _FakeCurlRequestsError("Unsupported protocol", code=1)
    fake_mod = _fake_curl_module(side_effect=curl_exc)
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.UnsupportedProtocol):
            await client.fetch_html(_URL, timeout=5.0)


async def test_curl_cffi_client_unknown_error_raises_connect_error():
    """Erro desconhecido (code=99) → httpx.ConnectError (fallback)."""
    curl_exc = _FakeCurlRequestsError("Unknown curl error", code=99)
    fake_mod = _fake_curl_module(side_effect=curl_exc)
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.ConnectError):
            await client.fetch_html(_URL, timeout=5.0)


# ─────────────────────────────────────────────────────────────────────────────
# Testes de respostas HTTP com status de erro
# ─────────────────────────────────────────────────────────────────────────────

async def test_curl_cffi_client_429_raises_http_status_error():
    """Resposta 429 → httpx.HTTPStatusError com status_code=429."""
    fake_mod = _fake_curl_module(response=_FakeResponse(status_code=429, body="<html>rate limited</html>"))
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.fetch_html(_URL, timeout=5.0)

    assert exc_info.value.response.status_code == 429


async def test_curl_cffi_client_403_raises_http_status_error():
    """Resposta 403 → httpx.HTTPStatusError com status_code=403."""
    fake_mod = _fake_curl_module(response=_FakeResponse(status_code=403, body="<html>forbidden</html>"))
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.fetch_html(_URL, timeout=5.0)

    assert exc_info.value.response.status_code == 403


async def test_curl_cffi_client_404_raises_http_status_error_without_escalation():
    """Resposta 404 → httpx.HTTPStatusError com status_code=404 (sem escalar para Playwright)."""
    fake_mod = _fake_curl_module(response=_FakeResponse(status_code=404, body="<html>not found</html>"))
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.fetch_html(_URL, timeout=5.0)

    assert exc_info.value.response.status_code == 404


async def test_curl_cffi_client_500_raises_http_status_error():
    """Resposta 500 → httpx.HTTPStatusError com status_code=500."""
    fake_mod = _fake_curl_module(response=_FakeResponse(status_code=500, body="<html>server error</html>"))
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.fetch_html(_URL, timeout=5.0)

    assert exc_info.value.response.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# Testes de limites de tamanho
# ─────────────────────────────────────────────────────────────────────────────

async def test_curl_cffi_client_respects_max_content_length(monkeypatch):
    """Corpo acima de SCRAPER_HTTP_MAX_CONTENT_LENGTH → ValueError."""
    import types
    from market_scraper.core.config_scraper import settings as _real_settings
    import market_scraper.utils.http_download as _dl_module

    # Pydantic v2 BaseSettings ignora setattr simples; patching o módulo diretamente.
    # Iteramos sobre model_fields da *classe* para evitar DeprecationWarning do Pydantic v2.11.
    field_names = set(_real_settings.__class__.model_fields.keys())
    fake_settings = types.SimpleNamespace(**{
        name: getattr(_real_settings, name) for name in field_names
    })
    fake_settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH = 10
    fake_settings.get_default_cookies = _real_settings.get_default_cookies
    fake_settings.resolve_domain_timeout = _real_settings.resolve_domain_timeout
    fake_settings.get_additional_headers = _real_settings.get_additional_headers
    monkeypatch.setattr(_dl_module, "settings", fake_settings)

    fake_mod = _fake_curl_module(response=_FakeResponse(status_code=200, body="x" * 20))
    with _inject_curl_module(fake_mod):
        client = CurlffiHTTPClient()
        with pytest.raises(ValueError, match="tamanho máximo"):
            await client.fetch_html(_URL, timeout=5.0)


# ─────────────────────────────────────────────────────────────────────────────
# Testes do enum CurlcffiErrorType
# ─────────────────────────────────────────────────────────────────────────────

def test_curl_cffi_error_type_values_are_stable():
    """Garante que os valores do enum não mudam acidentalmente."""
    assert CurlcffiErrorType.TIMEOUT.value == "timeout"
    assert CurlcffiErrorType.CONNECTION_ERROR.value == "connection_error"
    assert CurlcffiErrorType.TOO_MANY_REQUESTS.value == "too_many_requests"
    assert CurlcffiErrorType.ACCESS_DENIED.value == "access_denied"
    assert CurlcffiErrorType.NOT_FOUND.value == "not_found"
    assert CurlcffiErrorType.TOO_MANY_REDIRECTS.value == "too_many_redirects"
    assert CurlcffiErrorType.INVALID_URL.value == "invalid_url"
    assert CurlcffiErrorType.SERVER_ERROR.value == "server_error"
    assert CurlcffiErrorType.UNSUPPORTED_PROTOCOL.value == "unsupported_protocol"
