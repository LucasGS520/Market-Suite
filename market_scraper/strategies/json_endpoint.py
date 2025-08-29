""" Ponto de extração para estratégias baseadas em endpoints JSON nativos

Este módulo fornece classes de *stub* para futuras implementações de
scraping que consumam APIs públicas dos marketplaces. As classes atuais
simplesmente retornam ``{"status": "error"}``, permitindo que o fluxo
principal faça o **fallback** automático para outras estratégias.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse
import re
from decimal import Decimal

import httpx
from aiohttp import payload_type

from market_scraper.utils.constants import USER_AGENTS
from market_scraper.utils.data_quality_validator import DataQualityValidator

from .base import ScrapingStrategy


class JsonEndpointStrategy(ScrapingStrategy):
    """ Estratégia genérica para consumo de endpoints JSON

    A implementação padrão verifica apenas se a URL pertence ao domínio
    esperado e retorna um resultado de erro. As classes concretas devem
    sobrescrever ``get_data`` quando houver um endpoint disponível.
    """

    priority = 5
    domain: str = ""

    def supports_url(self, url: str) -> bool:
        """ Confere se a URL pertence ao domínio configurado """
        netloc = urlparse(url).netloc
        return netloc.endswith(self.domain)

    async def get_data(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> dict:
        """ Retorna erro indicando que não há implementação disponível """
        return {"status": "error"}


# ---------- ESTRATÉGIAS COM ENDPOINTS JSON POR MARKETPLACE ---------- #
class MercadoLivreJsonStrategy(JsonEndpointStrategy):
    """ Stub para futura coleta via API do Mercado Livre """
    domain = "mercadolivre.com.br"

class AmazonJsonStrategy(JsonEndpointStrategy):
    """ Stub para futura coleta via API da Amazon Brasil """
    domain = "amazon.com.br"

class ShopeeJsonStrategy(JsonEndpointStrategy):
    """ Estratégia que consome diretamente a API JSON pública da Shopee """
    domain = "shopee.com.br"

    async def get_data(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> dict:
        """ Obtém informações de produto via endpoint ``/api/v4/item/get``

        Parâmetros
        ----------
        url:
            Link original do produto na Shopee
        headers:
            Cabeçalhos opcionais a serem mesclados aos padrões. É útils para
            inserir identificadores de sessão ou personalizações externas.
        """
        #Extrai ``shopid`` e ``itemid`` presentes na URL
        parsed = urlparse(url)
        match = re.search(r"i\.(\d+)\.(\d+)", parsed.path)
        if not match:
            return {"status": "error"}
        shopid, itemid = match.groups()

        api_url = f"{parsed.scheme}://{parsed.netloc}/api/v4/item/get"

        #cabeçalhos mínimos exigidos pela API
        req_headers = {
            "User-Agent": (headers or {}).get("User-Agent", USER_AGENTS[0]),
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Referer": url,
        }
        if headers:
            req_headers.update(headers)

        async with httpx.AsyncClient(headers=req_headers, timeout=10) as client:
            #Primeira requisição opcional para popular cookies e possível CSRF
            try:
                await client.get(url)
            except httpx.HTTPError:
                #Falhas aqui não impedem fluxo principal
                pass

            #Adiciona cabeçalho de CSRF se o cookie estiver presente
            csrf = client.cookies.get("csrftoken")
            if csrf:
                client.headers["x-csrftoken"] = csrf

            params = {"itemid": itemid, "shopid": shopid}
            resp = await client.get(api_url, params=params)

            #Falhas de autenticação retornam erro simples para ativar fallback
            if resp.status_code in (401, 403):
                return {"status": "error"}

            resp.raise_for_status()
            payload = resp.json().get("data", {})

        #Formata o preço retornado pela API (valor inteiro em centavos * 1000)
        price_raw = payload.get("price")
        current_price = ""
        if price_raw is not None:
            try:
                price_dec = Decimal(str(price_raw)) / Decimal(100000)
                formatted = (
                    f"{price_dec:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
                )
                current_price = f"R$ {formatted}"
            except Exception:
                current_price = ""

        details = {"name": payload.get("name"), "url": url, "current_price": current_price}

        #Valida os dados coletas antes de retornar
        try:
            DataQualityValidator().validate(details)
        except Exception:
            return {"status": "error"}

        return {"status": "success", "details": details}


class MagaluJsonStrategy(JsonEndpointStrategy):
    """ Stub para futura coleta via API do Magalu """
    domain = "magazineluiza.com.br"


#Lista de classes exportadas para facilitar importações diretas
__all__ = [
    "JsonEndpointStrategy",
    "MercadoLivreJsonStrategy",
    "AmazonJsonStrategy",
    "ShopeeJsonStrategy",
    "MagaluJsonStrategy",
]
