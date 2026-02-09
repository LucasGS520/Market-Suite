""" Testes essenciais de utilidades HTTP e retry do scraper """

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from market_scraper.utils.http_retry import build_retrying_operation, _raise_for_retryable_response, RetryableHTTPError
from market_scraper.utils.http_utils import parse_retry_after


@pytest.mark.asyncio
async def test_build_retrying_operation_refaz_tentativa(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Valida que a operação é repetida quando ocorre erro transitório """
    #Reduzimos a política de retries para tornar o teste rápido e determinístico
    monkeypatch.setattr("market_scraper.utils.http_retry.settings.SCRAPER_HTTP_RETRIES", 1)
    monkeypatch.setattr("market_scraper.utils.http_retry.settings.SCRAPER_HTTP_RETRY_BACKOFF_BASE", 0.0)

    chamadas = {"total": 0}
    request = httpx.Request("GET", "https://exemplo.com")

    async def _operacao() -> httpx.Response:
        chamadas["total"] += 1
        if chamadas["total"] == 1:
            raise httpx.RequestError("falha", request=request)
        return httpx.Response(200, request=request)

    operação_retry = build_retrying_operation(target="exemplo", operation=_operacao)
    resposta = await operação_retry()

    assert resposta.status_code == 200
    assert chamadas["total"] == 2


def test_raise_for_retryable_response_dispara_excecao() -> None:
    """ Garante que respostas 5xx geram exceção de retry """
    request = httpx.Request("GET", "https://exemplo.com")
    response = httpx.Response(503, request=request, headers={"Retry-After": "2"})

    with pytest.raises(RetryableHTTPError) as excinfo:
        _raise_for_retryable_response(response, target="exemplo")

    assert excinfo.value.retry_after == 2.0
    assert excinfo.value.status_code == 503


def test_parse_retry_after_suporta_segundos_e_http_date() -> None:
    """ Confirma parsing de segundos e datas HTTP no Retry-After """
    assert parse_retry_after("1.5") == 1.5

    future = datetime.now(timezone.utc) + timedelta(seconds=60)
    http_date = format_datetime(future)
    resultado = parse_retry_after(http_date)

    assert resultado is not None
    assert resultado >= 0.0