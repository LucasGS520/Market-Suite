"""Facade pública da camada de persistência de coletores.

Reexporta somente operações de escrita/leitura de erros de coleta para manter
um contrato simples para consumidores externos.
"""

from market_alert.collectors.crud.crud_errors import create_scraping_error

__all__ = ["create_scraping_error"]
