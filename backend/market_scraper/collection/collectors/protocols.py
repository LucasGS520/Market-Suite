""" Portas (interfaces) da camada de coleta.

Define os contratos que qualquer implementação de coletor HTTP ou browser
deve satisfazer. A camada de domínio (use case, pipeline) depende apenas
destas interfaces — nunca de curl_cffi, Playwright ou Crawlee diretamente.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HttpCollector(Protocol):
    """ Porta para coleta de HTML via HTTP.

    Implementações concretas: CurlCFFIHttpCollector.
    """

    async def fetch(self, url: str, *, timeout: float) -> str:
        """ Obtém o HTML bruto da URL.

        Args:
            url: URL do produto.
            timeout: Orçamento em segundos para a requisição.

        Returns:
            HTML como string.

        Raises:
            httpx.HTTPStatusError: Resposta com status de erro.
            httpx.TooManyRedirects: Loop de redirecionamento.
            httpx.InvalidURL | httpx.UnsupportedProtocol: URL inválida.
        """
        ...


@runtime_checkable
class BrowserCollector(Protocol):
    """ Porta para coleta de HTML via browser headless.

    Implementações concretas: PlaywrightBrowserCollector.
    """

    @property
    def is_ready(self) -> bool:
        """ Indica se o pool de browser está disponível para receber requisições."""
        ...

    async def fetch(
        self,
        url: str,
        *,
        timeout: float,
        domain: str | None = None,
    ) -> str:
        """ Obtém o HTML renderizado pelo browser.

        Args:
            url: URL do produto.
            timeout: Orçamento em segundos para renderização.
            domain: Hostname para reutilização de sessão persistente.

        Returns:
            HTML renderizado como string.

        Raises:
            PlaywrightPoolNotReadyError: Pool não está pronto.
            PlaywrightTimeoutError: Timeout de renderização.
            PlaywrightFetchError: Erro de navegação.
        """
        ...


__all__ = ["BrowserCollector", "HttpCollector"]
