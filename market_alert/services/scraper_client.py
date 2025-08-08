""" Cliente HTTP para o serviço externo de scraping

Este módulo centraliza as requisições ao ``market_scraper``,
fornecendo tratamento de erros e mensagens mais claras
para os chamadores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import requests

from alert_app.core.config import settings


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

    def parse(self, url: str, product_type: str, **extra: Any) -> Dict[str, Any]:
        """ Envia requisição ``POST`` ao endpoint de parsing

        Args:
            url: Endereço do produto que serã analisado
            product_type: Tipo de produto (``monitored`` ou ``competitor``)
            **extra: Campos adicionais enviados no ``payload``

        Returns:
            Dicionário com os dados retornados pelo serviço de scraping

        Raises:
            ScraperClientError: Em casos de ``timeout`` ou respostas ``4xx/5xx``
        """

        payload = {"url": url, "product_type": product_type} | extra

        try:
            resp = requests.post(
                f"{self.base_url}/scraper/parse",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout as exc:
            raise ScraperClientError(
                "Tempo limite excedido ao chamar o serviço de scraping"
            ) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response else 500
            raise ScraperClientError(
                f"Erro HTTP {status} ao chamar o serviço de scraping", status
            ) from exc
        except requests.RequestException as exc:
            raise ScraperClientError(
                f"Falha na comunicação com o serviço de scraping: {exc}"
            ) from exc
