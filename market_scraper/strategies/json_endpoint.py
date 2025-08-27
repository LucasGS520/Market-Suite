from __future__ import annotations

""" Estratégias leves baseadas em JSON-LD e meta tags """

from typing import Optional, Dict, Any
import json
from decimal import Decimal

import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from .base import ScrapingStrategy
from market_scraper.utils.humanized_delay import HumanizedDelayManager
from market_scraper.utils.throttle_manager import ThrottleManager
from market_scraper.utils.constants import THROTTLE_RATE, THROTTLE_CAPACITY, JITTER_RANGE, STEALTH_HEADERS
from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.services.services_cache_scraper import get_cached_html, set_cached_html


class JsonEndpointStrategy(ScrapingStrategy):
    """ Estratégia genérica que busca via JSON-LD ou meta tags

    A classe realiza uma requisição HTTP simples para obter o conteúdo HTML,
    procurando blocos ``JSON-LD`` ou meta tags com informações básicas do produto.
    A respota é validada pelo ``DataQualityValidator`` e o HTMl é armazenado no cache.
    """

    priority = 10
    domain: str = ""

    def supports_url(self, url: str) -> bool:
        """ Verifica se a URL pertence ao domínio alvo

        A validação utiliza ``urlparse`` para extrair o ``netloc`` da URL
        (host) e confirma que ele termina com o domínio esperado, permitindo
        que subdomínios legítimos sejam aceitos e evitando coincidências
        parciais em outros domínios.
        """
        netloc = urlparse(url).netloc
        return netloc.endswith(self.domain)

    async def _fetch_html(self, url: str) -> str:
        """ Obtém o HTML com controle de atraso e cache """
        cached = await get_cached_html(url)
        if cached:
            return cached

        throttle = ThrottleManager(THROTTLE_RATE, THROTTLE_CAPACITY, JITTER_RANGE)
        human = HumanizedDelayManager()
        await human.wait_async(None)
        await throttle.wait_async(circuit_key="json", identifier=self.domain)

        async with httpx.AsyncClient(headers=STEALTH_HEADERS, timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        await set_cached_html(url, html)
        return html

    def _format_price(self, price: Any, currency: Optional[str]) -> str:
        """ Formata preço numérico no padrão brasileiro """
        if price is None:
            return ""
        try:
            value = Decimal(str(price))
        except Exception:
            return ""
        symbol = "R$" if (currency or "").upper() in {"BRL", "R$"} else (currency or "")
        formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return f"{symbol} {formatted}".strip()

    def _extract_from_json_ld(self, soup: BeautifulSoup, url: str) -> dict:
        """ Procura blocos JSON-LD e extrai dados de produto """
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                content = json.loads(tag.string or "{}")
            except json.JSONDecodeError:
                continue
            items = []
            if isinstance(content, dict):
                items = content.get("@graph", []) if "@graph" in content else [content]
            elif isinstance(content, list):
                items = content
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    name = item.get("name") or item.get("description") or item.get("sku")
                    offers = item.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price = offers.get("price") or offers.get("priceSpecification", {}).get("price")
                    currency = offers.get("priceCurrency") or offers.get("priceSpecification", {}).get("priceCurrency")
                    image = item.get("image")
                    seller = item.get("brand") or item.get("seller")
                    if isinstance(seller, dict):
                        seller = seller.get("name")
                    data = {
                        "name": name,
                        "url": url,
                        "current_price": self._format_price(price, currency),
                        "thumbnail": image or url,
                        "seller": seller or self.domain,
                    }
                    return data
        return {}

    def _extract_from_meta_tags(self, soup: BeautifulSoup, url: str) -> dict:
        """ Extrai dados de meta-tags como fallback """
        name = (
            soup.find("meta", property="og:title") or soup.find("title")
        )
        price = (
            soup.find("meta", itemprop="price") or soup.find("meta", property="product:price:amount")
        )
        currency = (
            soup.find("meta", property="product:price:currency") or soup.find("meta", itemprop="priceCurrency")
        )
        image = soup.find("meta", property="og:image")
        seller = soup.find("meta", property="og:site_name")

        data = {
            "name": name.get("content") if name else None,
            "url": url,
            "current_price": self._format_price(
                price.get("content") if price else None,
                currency.get("content") if currency else None,
            ),
            "thumbnail": image.get("content") if image else url,
            "seller": seller.get("content") if seller else self.domain,
        }
        return data

    def _parse_html(self, html: str, url: str) -> dict:
        """ Orquestra a extração dos dados """
        soup = BeautifulSoup(html, "html.parser")
        data = self._extract_from_json_ld(soup, url)
        #Caso o JSON-LD não forneça um nome de produto, recorre ás meta tags
        if not data or not data.get("name"):
            data = self._extract_from_meta_tags(soup, url)
        return data

    async def get_data(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> dict:
        """ Executa o fluxo de scraping leve """
        try:
            html = await self._fetch_html(url)
            data = self._parse_html(html, url)
            DataQualityValidator().validate(data)
            return {"status": "success", "details": data}
        except Exception as err:
            return {"status": "error", "details": str(err)}

# ---------- JSON ENDPOINT DOS MARKETPLACES ----------
class MercadoLivreJsonEndpointStrategy(JsonEndpointStrategy):
    """ Estratégia para páginas do Mercado Livre """
    domain = "mercadolivre.com.br"

class AmazonJsonEndpointStrategy(JsonEndpointStrategy):
    """ Estratégia para páginas da Amazon Brasil """
    domain = "amazon.com.br"

class ShopeeJsonEndpointStrategy(JsonEndpointStrategy):
    """ Estratégia para páginas da Shopee """
    domain = "shopee.com"

class MagaluJsonEndpointStrategy(JsonEndpointStrategy):
    """ Estratégia para páginas do Magazine Luiza """
    domain = "magazineluiza.com.br"


__all__ = [
    "JsonEndpointStrategy",
    "MercadoLivreJsonEndpointStrategy",
    "AmazonJsonEndpointStrategy",
    "ShopeeJsonEndpointStrategy",
    "MagaluJsonEndpointStrategy",
]
