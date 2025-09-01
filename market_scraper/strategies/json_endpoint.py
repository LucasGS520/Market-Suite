""" Ponto de extração para estratégias baseadas em endpoints JSON nativos

Este módulo fornece classes de *stub* para futuras implementações de
scraping que consumam APIs públicas dos marketplaces. As classes atuais
simplesmente retornam ``{"status": "error"}``, permitindo que o fluxo
principal faça o **fallback** automático para outras estratégias.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs
import re
from decimal import Decimal

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.utils.intelligent_cache import IntelligentCacheManager
from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager

#Gerenciador de cache reutilizado para chamadas ao endpoint da Shopee
cache_manager = IntelligentCacheManager()

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

    #Gerenciador de User-Agent para rotacionar cabeçalhos em cada requisição
    _ua_manager = IntelligentUserAgentManager()

    async def get_data(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> dict:
        """ Obtém informações de produto via endpoint ``/api/v4/item/get``

        O ``User-Agent`` é rotacionado a cada requisição para reduzir
        bloqueios e imitar acessos de navegadores distintos.

        Parâmetros
        ----------
        url:
            Link original do produto na Shopee
        headers:
            Cabeçalhos opcionais a serem mesclados aos padrões. É útils para
            inserir identificadores de sessão ou personalizações externas.
        """
        #Verifica se há dados recentes de produto em cache para evitar nova requisição
        cached = cache_manager.get(marketplace="shopee", url=url)
        if cached is not None:
            #O cache armazena somente os dados do produto
            return {"status": "success", "details": cached}

        #Extrai ``shopid`` e ``itemid`` do caminho ou dos parâmetros da URL
        parsed = urlparse(url)
        shopid: Optional[str] = None
        itemid: Optional[str] = None

        match = re.search(r"i\.(\d+)\.(\d+)", parsed.path)
        if match:
            shopid, itemid = match.groups()
        else:
            qs_params = parse_qs(parsed.query)
            shopid = qs_params.get("shopid", [None])[0]
            itemid = qs_params.get("itemid", [None])[0]

        if not shopid or not itemid:
            return {"status": "error"}

        api_url = f"{parsed.scheme}://{parsed.netloc}/api/v4/item/get"

        #cabeçalhos mínimos exigidos pela API
        req_headers = {
            "User-Agent": (headers or {}).get(
                "User-Agent", self._ua_manager.get_user_agent("shopee_json")
            ),
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

            async def _retryable(exc: Exception) -> bool:
                """ Define quais exceções devem ser consideradas transitórias """
                if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                    code = exc.response.status_code
                    return code == 429 or code >= 500
                return isinstance(exc, httpx.HTTPError)

            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=1, max=4),
                    retry=retry_if_exception(_retryable),
                    reraise=True,
                ):
                    with attempt:
                        resp = await client.get(api_url, params=params)
                        if resp.status_code in (401, 403):
                            return {"status": "error"}
                        resp.raise_for_status()
                        #Tenta decodificar o JSON da resposta; se falhar, retorna erro
                        try:
                            payload = resp.json().get("data", {})
                        except ValueError:
                            return {"status": "error"}
            except httpx.HTTPError:
                return {"status": "error"}

        #Formata o preço retornado pela API (valor inteiro em centavos * 1000)
        price_raw = payload.get("price")

        #Caso ``price`` não exista, tenta campos alternativas de preço
        if price_raw is None:
            for fallback_key in ("price_min", "price_max", "price_before_discount"):
                price_raw = payload.get(fallback_key)
                if price_raw is not None:
                    break
            else:
                models = payload.get("models") or []
                if isinstance(models, list) and models:
                    price_raw = models[0].get("price")

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

        result = {"status": "success", "details": details}
        #Salva apenas os detalhes do produto no cache para reutilizações futuras
        cache_manager.set(marketplace="shopee", url=url, value=details)
        return result


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
