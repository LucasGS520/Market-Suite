""" Portas (interfaces) da camada de coleta — HTTP e browser collectors. """

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HttpCollector(Protocol):
    """ Porta para coleta de HTML via HTTP com impersonation.

    Implementação concreta: HttpCollector em http_collector.py.
    """

    @property
    def is_ready(self) -> bool:
        """ Indica se o client HTTP está disponível."""
        ...

    async def fetch(
        self,
        url: str,
        *,
        timeout: float,
        bound_logger: object | None = None,
    ) -> tuple[str | None, int | None, Exception | None, str | None]:
        """ Executa requisição HTTP.

        Retorna (html, http_status, error, error_code).
        """
        ...


@runtime_checkable
class BrowserCollector(Protocol):
    """ Porta para coleta de HTML via browser headless.

    Implementação concreta: PlaywrightBrowserCollector.
    """

    @property
    def is_ready(self) -> bool:
        """ Indica se o browser está disponível para receber requisições."""
        ...

    async def fetch(
        self,
        url: str,
        *,
        timeout: float,
        domain: str | None = None,
    ) -> str:
        """ Obtém o HTML renderizado pelo browser.

        Raises:
            PlaywrightPoolNotReadyError: Browser não está pronto.
            PlaywrightTimeoutError: Timeout de renderização.
            PlaywrightFetchError: Erro de navegação.
        """
        ...


__all__ = ["BrowserCollector", "HttpCollector"]
