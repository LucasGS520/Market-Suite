from __future__ import annotations

""" Estratégia baseadas em HTML estático """

import json
import re
from decimal import Decimal
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .base import ScrapingStrategy
from market_scraper.utils.constants import STEALTH_HEADERS, GENERIC_COOKIES
from market_scraper.utils.data_quality_validator import DataQualityValidator


class HtmlStaticStrategy(ScrapingStrategy):
    """ Estratégia genérica que realiza scraping em HTML estático

    A classe efetua uma requisição HTTP simples utilizando ``httpx`` com
    cabeçalhos de navegação realistas e cookies padrão definidos em
    ``STEALTH_HEADERS`` e ``GENERIC_COOKIES``. Em seguida tenta obter o
    nome e o preço do produto a partir de blocos ``JSON-LD`` (quando ``@type``
    é ``Product``). Caso esses dados não estejam presentes, é realizado um fallback
    para meta tags e seletores simples. Os campos resultantes são validados pelo
    ``DataQualityValidator``.
    """

    priority = 10
    domain: str = ""

    def supports_url(self, url: str) -> bool:
        """ Verifica se a URL pertence ao domínio esperado """
        netloc = urlparse(url).netloc
        return netloc.endswith(self.domain)

    async def _fetch_html(self, url: str) -> str:
        """ Baixa o HTML utilizando ``httpx`` com cabeçalhos stealth e ``Referer`` dinâmico

        Antes de realizar a requisição, o domínio base da URL é calculado para
        preencher o cabeçalho ``Referer`` com o formato
        ``<esquema>://<domínio>/``. Dessa forma, cada site recebe um valor
        coerente e evita bloqueios por referências incorretas
        """
        parsed = urlparse(url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}/"
        headers = {**STEALTH_HEADERS, "Referer": base_domain}

        async with httpx.AsyncClient(headers=headers, cookies=GENERIC_COOKIES, timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    def _format_price(self, value: Any, currency: Optional[str]) -> str:
        """ Formata um valor numérico para o padrão monetário brasileiro """
        if value is None:
            return ""
        try:
            amount = Decimal(str(value))
        except Exception:
            return ""
        symbol = "R$" if not currency or (currency or "").upper() in {"BRL", "R$"} else (currency or "")
        formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return f"{symbol} {formatted}".strip()


    def _extract_from_json_ld(self, soup: BeautifulSoup, url: str) -> dict:
        """ Procura blocos JSON-LD de produto e extrai informações principais """
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                content = json.loads(tag.string or "{}")
            except json.JSONDecodeError:
                continue
            itens: list[Any]
            if isinstance(content, dict):
                itens = content.get("@graph", []) if "@graph" in content else [content]
            elif isinstance(content, list):
                itens = content
            else:
                itens = []
            for item in itens:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    name = item.get("name") or item.get("description") or item.get("sku")
                    offers = item.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price = offers.get("price") or offers.get("priceSpecification", {}).get("price")
                    #Busca a moeda diretamente ou dentro de ``priceSpecification``
                    currency = offers.get("priceCurrency") or offers.get("priceSpecification", {}).get("priceCurrency")
                    return {
                        "name": name,
                        "url": url,
                        "current_price": self._format_price(price, currency),
                    }
        return {}

    def _extract_from_meta_tags(self, soup: BeautifulSoup, url: str) -> dict:
        """ Extrai dados de meta-tags como alternativa ao JSON-LD """
        name = soup.find("meta", property="og:title") or soup.find("title")
        price = soup.find("meta", itemprop="price") or soup.find("meta", property="product:price:amount")
        currency = soup.find("meta", property="product:price:currency") or soup.find("meta", itemprop="priceCurrency")

        #Determina o valor do nome considerando meta-tags e a tag <title>
        name_value: Optional[str] = None
        if name:
            if name.name == "meta":
                #Em meta-tags o nome é definido pelo atributo ``content``
                name_value = name.get("content")
            else:
                #Para a tag <title> utilizamos o texto interno
                name_value = name.text

        return {
            "name": name_value,
            "url": url,
            "current_price": self._format_price(
                price.get("content") if price else None,
                currency.get("content") if currency else None,
            )
        }

    def _parse_html(self, html: str, url: str) -> dict:
        """ Orquestra a extração dos dados do HTML informado """
        soup = BeautifulSoup(html, "html.parser")
        data = self._extract_from_json_ld(soup, url)
        if not data or not data.get("name"):
            data = self._extract_from_meta_tags(soup, url)
        return data

    async def get_data(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> dict:
        """ Executa o scraping e trata falhas de validação dos dados """
        html = await self._fetch_html(url)
        data = self._parse_html(html, url)
        try:
            #Valida apenas os campos essenciais antes de retornar
            DataQualityValidator(["name", "current_price"]).validate(data)
        except ValueError:
            #Caso a validação falhe, a estratégia sinaliza erro
            return {"status": "error"}
        return {"status": "success", "details": data}


# ---------- ESTRATÉGIA DO HTML ESTÁTICO DOS MARKETPLACES ---------- #
class MercadoLivreHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas do Mercado Livre """
    domain = "mercadolivre.com.br"

    def _parse_html(self, html: str, url: str) -> dict:
        """ Extrai nome e preço de páginas do Mercado Livre

        A função inicia tentando os métodos genéricos de extração
        (JSON-LD e meta tags). Caso não obtenha os dados essenciais,
        realiza um fallback utilizando seletores específicos do site.
        """
        soup = BeautifulSoup(html, "html.parser")

        #Primeiro tenta reutilizar os extratores da estratégia base
        data = self._extract_from_json_ld(soup, url)
        if not data.get("name") or not data.get("current_price"):
            data = self._extract_from_meta_tags(soup, url)

        #Se já houver nome e preço válidos, retorna imediatamente
        if data.get("name") and data.get("current_price"):
            return data

        # --- FALLBACK PARA SELETORES ESPECÍFICOS DO MERCADO LIVRE ---

        #Título do produto em h1.ui-pdp-title ou meta[name="title"]
        #Como último recurso utiliza ``soup.find(`h1`)`` caso as alternativas específicas não estejam presentes
        title_tag = soup.select_one("h1.ui-pdp-title")
        meta_title = soup.find("meta", attrs={"name": "title"})
        generic_h1 = soup.find("h1") if not title_tag and not meta_title else None
        title: Optional[str] = None
        if title_tag:
            title = title_tag.get_text(strip=True)
        elif meta_title:
            title = meta_title.get("content")

        elif generic_h1:
            title = generic_h1.get_text(strip=True)

        #Preço pode estar em diversas combinações de classes
        fraction = (
            soup.select_one(".andes-money-amount__fraction")
            or soup.select_one(".price-tag-fraction")
            or soup.find("span", {"class": "price-tag-fraction"})
        )
        cents = (
            soup.select_one(".andes-money-amount__cents")
            or soup.select_one(".price-tag-decimal")
        )

        value: Optional[str] = None
        if fraction:
            #Remove separadores de milhar e outros caracteres da parte inteira
            whole_part = re.sub(r"\D", "", fraction.get_text())
            value = whole_part
            if cents:
                decimal_part = re.sub(r"\D", "", cents.get_text())
                #Concatena parte inteira e decimal para formar o valor
                value = f"{value}.{decimal_part}"

        else:
            #Fallback para ``span[itemprop=`price`]`` caso não exista estrutura de fração/centavos
            itemprop_price = soup.find("span", itemprop="price")
            if itemprop_price:
                raw_price = itemprop_price.get("content") or itemprop_price.get_text(strip=True)
                cleaned = re.sub(r"[^\d.,]", "", raw_price)
                if "," in cleaned and "." in cleaned:
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                else:
                    cleaned = cleaned.replace(",", ".")
                value = cleaned or None

        #Busca a moeda em meta tags específicas caso esteja disponível
        currency_tag = (
            soup.find("meta", itemprop="priceCurrency")
            or soup.find("meta", property="product:price:currency")
        )
        currency_value=currency_tag.get("content") if currency_tag else None

        return {
            "name": title,
            "url": url,
            #Normaliza o valor monetário utilizando a função da classe base
            "current_price": self._format_price(value, currency_value),
        }


class AmazonHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas da Amazon Brasil """
    domain = "amazon.com.br"


class ShopeeHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas da Shopee """
    domain = "shopee.com.br"


class MagaluHtmlStaticStrategy(HtmlStaticStrategy):
    """ Estratégia para páginas estáticas do Magazine Luiza """
    domain = "magazineluiza.com.br"


__all__ = [
    "HtmlStaticStrategy",
    "MercadoLivreHtmlStaticStrategy",
    "AmazonHtmlStaticStrategy",
    "ShopeeHtmlStaticStrategy",
    "MagaluHtmlStaticStrategy",
]
