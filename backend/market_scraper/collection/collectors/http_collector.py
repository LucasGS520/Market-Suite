""" Implementação concreta de HttpCollector via curl_cffi.

Delega para download_html (utils/http_download.py) sem expor
detalhes de curl_cffi para a camada de orquestração.
"""

from __future__ import annotations

from market_scraper.utils.http_download import download_html


class CurlCFFIHttpCollector:
    """ HttpCollector usando curl_cffi com fingerprint TLS de browser.

    Stateless e thread-safe — pode ser instanciada uma vez e compartilhada.
    Todas as decisões de retry, headers e fingerprint ficam em download_html.
    """

    async def fetch(self, url: str, *, timeout: float) -> str:
        """Delega para download_html preservando semântica de exceções."""
        return await download_html(url, timeout=timeout)


__all__ = ["CurlCFFIHttpCollector"]
