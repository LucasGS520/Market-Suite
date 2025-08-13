""" Módulo que provê um cliente HTTP assíncrono para interagir com
o serviço externo de scraping ``market_scraper``

Envia requisições de parsing para páginas de produtos e retorna
os dados estruturados, tratando erros de comunicação com o serviço
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import httpx

from market_alert.core.config import settings


class ScraperClientError(Exception):
    """ Erro de comunicação com o serviço ``market_scraper``

    Attributes:
        status_code: Código HTTP retornado, quando disponível
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

@dataclass
class ScraperClient:
    """ Cliente simples para interagir com o ``market_scraper`` """

    base_url: str = settings.SCRAPER_SERVICE_URL

    async def parse(self, url: str, product_type: str, **extra: Any) -> Dict[str, Any]:
        """ Envia requisição ``POST`` ao endpoint de parsing de forma assíncrona

        Args:
            url: Endereço do produto que será analisado
            product_type: Tipo de produto (``monitored`` ou ``competitor``)
            **extra: Campos adicionais enviados no ``payload``

        Returns:
            Dicionário com os dados retornados pelo serviço de scraping

        Raises:
            ScraperClientError: Em casos de ``timeout`` ou respostas ``4xx/5xx``
        """

        payload = {"url": url, "product_type": product_type} | extra

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/scraper/parse",
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException as exc:
            raise ScraperClientError(
                "Tempo limite excedido ao chamar o serviço de scraping",
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else 500
            raise ScraperClientError(
                f"Erro HTTP {status} ao chamar o serviço de scraping", status
            ) from exc
        except httpx.RequestError as exc:
            raise ScraperClientError(
                f"Falha na comunicação com o serviço de scraping: {exc}"
            ) from exc
