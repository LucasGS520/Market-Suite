from __future__ import annotations

""" Funções utilitárias para extração de dados em páginas HTML estáticas

O módulo concentra toda a lógica de parsing utilizada pelos marketplaces
que expõem conteúdo estático. Cada função pública recebe o HTML bruto e a
URL original, devolvendo um dicionário com os campos essenciais
(``name`` e ``current_price``) para uso no pipeline de scraping.
"""

import json
import re
from decimal import Decimal
from time import perf_counter
from typing import Any, Dict, Optional

import structlog
from bs4 import BeautifulSoup
from parsel import Selector

from shared.metrics.metrics_parser import PARSER_FAILURE_TOTAL, PARSER_SUCCESS_TOTAL, PARSER_DURATION_SECONDS
from shared.utils.logging_utils import sanitize_log_data

from market_scraper.utils.extract_structured_data import extract_structured_data


#Logger estruturado para acompanhar eventos de scraping
logger = structlog.get_logger(__name__)


def _format_price(value: Any, currency: Optional[str]) -> str:
    """ Formata valores numéricos para o padrão monetário brasileiro.
    
    O helper aceita valores numéricos ou strings com separadores decimais,
    converte para ``Decimal`` e aplica o símbolo adequado (``R$`` por padrão
    ou o informado no ``currency``). Quando a conversão falha, retorna string
    vazia para indicar ausência de preço.
    """
    if value is None:
        return ""
    try:
        amount = Decimal(str(value))
    except Exception:
        return ""
    symbol = (
        "R$"
        if not currency or (currency or "").upper() in {"BRL", "R$"}
        else (currency or "")
    )
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{symbol} {formatted}".strip()

def _extract_from_structured_data(data: Dict[str, Any], url: str) -> dict:
    """ Obtém ``name`` e ``current_price`` a partir de blocos estruturados """
    for item in data.get("json-ld", []):
        if isinstance(item, dict) and item.get("@type") == "Product":
            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            elif isinstance(offers, dict) and isinstance(offers.get("offers"), list):
                offers = offers["offers"][0] if offers["offers"] else {}
            price = (
                offers.get("price")
                or offers.get("priceSpecification", {}).get("price")
                or offers.get("lowPrice")
                or offers.get("highPrice")
            )
            currency = (
                offers.get("priceCurrency")
                or offers.get("priceSpecification", {}).get("priceCurrency")
            )
            name = item.get("name") or item.get("description") or item.get("sku")
            return {
                "name": name, 
                "url": url,
                "current_price": _format_price(price, currency),
            }

    for item in data.get("microdata", []):
        types = item.get("type", [])
        if any("Product" in t for t in types):
            props = item.get("properties", {})
            name = props.get("name") or props.get("description") or props.get("sku")
            offers = props.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = (
                offers.get("price")
                or offers.get("priceSpecification", {}).get("price")
                or offers.get("lowPrice")
                or offers.get("highPrice")
            )
            currency = (
                offers.get("priceCurrency")
                or offers.get("priceSpecification", {}).get("priceCurrency")
            )
            return {
                "name": name, 
                "url": url,
                "current_price": _format_price(price, currency),
            }

    og = data.get("opengraph") or {}
    if isinstance(og, list):
        og = og[0] if og else {}
    if og.get("og:type") == "product":
        name = og.get("og:title")
        price = og.get("product:price:amount") or og.get("og:price:amount")
        currency = og.get("product:price:currency") or og.get("og:price:currency")
        return {
            "name": name,
            "url": url,
            "current_price": _format_price(price, currency),
        }

    return {}

        
def _extract_from_json_ld_parsel(sel: Selector, url: str) -> dict:
    """ Extrai JSON-LD (prioritário) com suporte a ``@graph``/listas """
    home = perf_counter()
    try:
        scripts = sel.xpath('//script[@type="application/ld+json"]/text()').getall()
        for raw in scripts:
            try:
                content = json.loads(raw or "{}")
            except json.JSONDecodeError as exc:
                logger.debug(
                    "JSON inválido em script JSON-LD",
                    url=sanitize_log_data(url),
                    erro=sanitize_log_data(str(exc)),
                )
                continue
                
            if isinstance(content, dict):
                items: list[Any] = content.get("@graph", []) if "@graph" in content else [content]
            elif isinstance(content, list):
                items = content
            else:
                items = []
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    name = item.get("name") or item.get("description") or item.get("sku")
                    offers = item.get("offers") or {}
                    if isinstance(offers, list):

                        offers = offers[0] if offers else {}
                    elif isinstance(offers, dict) and isinstance(offers.get("offers"), list):
                        offers = offers["offers"][0] if offers["offers"] else {}
                    price = (
                        offers.get("price")
                        or offers.get("priceSpecification", {}).get("price")
                        or offers.get("lowPrice")
                        or offers.get("highPrice")
                    )
                    currency = (
                        offers.get("priceCurrency")
                        or offers.get("priceSpecification", {}).get("priceCurrency")
                    )
                    PARSER_SUCCESS_TOTAL.labels(library="parsel").inc()
                    return {
                        "name": name, 
                        "url": url,
                        "current_price": _format_price(price, currency),
                    }
        PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
        return {}
    except Exception as exc:  # pragma: no cover - log defensivo
        PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
        logger.exception(
            "Erro ao extrair JSON-LD com Parsel",
            url=sanitize_log_data(url),
            erro=sanitize_log_data(str(exc)),
        )
        return {}
    finally:
        PARSER_DURATION_SECONDS.labels(library="parsel").observe(perf_counter() - home)


def _extract_from_meta_tags_parsel(sel: Selector, url: str) -> dict:
    """ Extrai ``name`` e ``current_price`` de meta-tags utilizando Parsel """
    home = perf_counter()
    try:
        name_value = (
            sel.css('meta[property="og:title"]::attr(content)').get()
            or sel.css("title::text").get()
        )
        price_value = (
            sel.css('meta[itemprop="price"]::attr(content)').get()
            or sel.css('meta[property="og:price:amount"]::attr(content)').get()
            or sel.css('meta[property="product:price:currency"]::attr(content)').get()
        )
        currency_value = (
            sel.css('meta[itemprop="priceCurrency"]::attr(content)').get()
            or sel.css('meta[property="og:price:currency"]::attr(content)').get()
            or sel.css('meta[property="product:price:currency"]::attr(content)').get()
        )
        data = {
            "name": name_value,
            "url": url,
            "current_price": _format_price(price_value, currency_value),
        }
        if data.get("name") and data.get("current_price"):
            PARSER_SUCCESS_TOTAL.labels(library="parsel").inc()
        else:
            PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
        return data
    
    except Exception as exc:
        PARSER_FAILURE_TOTAL.labels(library="parsel").inc()
        logger.exception(
            "Erro ao extrair meta-tags com Parsel",
            url=sanitize_log_data(url),
            erro=sanitize_log_data(str(exc)),
        )
        return {}
    finally:
        PARSER_DURATION_SECONDS.labels(library="parsel").observe(perf_counter() - home)


def _extract_from_json_ld(soup: BeautifulSoup, url: str) -> dict:
    """ Procura JSON-LD (Product) utilizando BeautifulSoup """
    home = perf_counter()
    try:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                content = json.loads(tag.string or "{}")
            except json.JSONDecodeError as exc:
                logger.debug(
                    "JSON inválido em script JSON-LD (bs4)",
                    url=sanitize_log_data(url),
                    erro=sanitize_log_data(str(exc)),
                )
                continue
            if isinstance(content, dict):
                items: list[Any] = content.get("@graph", []) if "@graph" in content else [content]
            elif isinstance(content, list):
                items = content
            else:
                items = []
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    name = item.get("name") or item.get("description") or item.get("sku")
                    offers = item.get("offers") or {}
                    
                    #Caso ``offers`` seja uma lista, utiliza o primeiro elemento
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    #Alguns sites definem ``offers`` dentro do outro bloco ``offers`` conforme o padrão ``AggregateOffer``.
                    elif isinstance(offers, dict) and isinstance(offers.get("offers"), list):
                        offers = offers["offers"][0] if offers["offers"] else {}

                    #Busca o preço em diferentes campos, incluindo ``lowPrice`` e ``highPrice`` quando ``price`` não estiver disponível.
                    price = (
                        offers.get("price")
                        or offers.get("priceSpecification", {}).get("price")
                        or offers.get("lowPrice")
                        or offers.get("highPrice")
                    )
                    #Busca a moeda diretamente ou dentro de ``priceSpecification``
                    currency = (
                        offers.get("priceCurrency")
                        or offers.get("priceSpecification", {}).get("priceCurrency")
                    )
                    PARSER_SUCCESS_TOTAL.labels(library="beautifulsoup").inc()
                    return {
                        "name": name,
                        "url": url,
                        "current_price": _format_price(price, currency),
                    }
        PARSER_FAILURE_TOTAL.labels(library="beautifulsoup").inc()
        return {}
    except Exception as exc:
        PARSER_FAILURE_TOTAL.labels(library="beautifulsoup").inc()
        logger.exception(
            "Erro ao extrair JSON-LD com BeautifulSoup",
            url=sanitize_log_data(url),
            erro=sanitize_log_data(str(exc)),
        )
        return {}
    finally:
        PARSER_DURATION_SECONDS.labels(library="beautifulsoup").observe(perf_counter() - home)

 
def _extract_from_meta_tags(soup: BeautifulSoup, url: str) -> dict:
    """ Extrai dados de meta-tags (fallback) com BeautifulSoup """
    home = perf_counter()
    try:
        name_tag = soup.find("meta", property="og:title") or soup.find("title")
        price_tag = (
            soup.find("meta", itemprop="price")
            or soup.find("meta", property="og:price:amount")
            or soup.find("meta", property="product:price:amount")
        )
        currency_tag = (
            soup.find("meta", itemprop="priceCurrency")
            or soup.find("meta", property="og:price:currency")
            or soup.find("meta", property="product:price:currency")
        )
        name_value: Optional[str] = None
        
        if name_tag:
            if name_tag.name == "meta":
                name_value = name_tag.get("content")
            else:
                name_value = name_tag.text

        data = {
            "name": name_value,
            "url": url,
            "current_price": _format_price(
                price_tag.get("content") if price_tag else None,
                currency_tag.get("content") if currency_tag else None,
            ),
        }
        if data.get("name") and data.get("current_price"):
            PARSER_SUCCESS_TOTAL.labels(library="beautifulsoup").inc()
        else:
            PARSER_FAILURE_TOTAL.labels(library="beautifulsoup").inc()
        return data
    except Exception as exc:
        PARSER_FAILURE_TOTAL.labels(library="beautifulsoup").inc()
        logger.exception(
            "Erro ao extrair meta-tags com BeautifulSoup",
            url=sanitize_log_data(url),
            erro=sanitize_log_data(str(exc)),
        )
        return {}
    finally:
        PARSER_DURATION_SECONDS.labels(library="beautifulsoup").observe(perf_counter() - home)


def parse_generic_html(html: str, url: str) -> dict:
    """ Extrai informações usando apenas seletores genéricos.
    
    A função combina extração de dados estruturados com Parsel e
    BeautifulSoup para lidar com páginas que não exigem regras
    específicas. O retorno sempre inclui a URL recebida.
    """
    structured = extract_structured_data(html, url)
    data = _extract_from_structured_data(structured, url)
    if data.get("name") and data.get("current_price"):
        return data
    
    sel = Selector(text=html)
    data = _extract_from_json_ld_parsel(sel, url)
    if data.get("name") and data.get("current_price"):
        return data
    data = _extract_from_meta_tags_parsel(sel, url)
    if data.get("name") and data.get("current_price"):
        return data

    soup = BeautifulSoup(html, "lxml")
    data = _extract_from_json_ld(soup, url)
    if data.get("name") and data.get("current_price"):
        return data
    data = _extract_from_meta_tags(soup, url)
    return data

def parse_meli_html(html: str, url: str) -> dict:
    """ Extrai dados de páginas do Mercado Livre.
    
    Parâmetros
    ----------
    html: str
        Conteúdo HTML completo da página de produto.
    url: str
        Endereço original utilizando para o scraping.

    Retorna
    -------
    dict
        Dicionário com os campos ``name``, ``current_price`` e ``url``.
    """
    data = parse_generic_html(html, url)
    if data.get("name") and data.get("current_price"):
        return data

    sel = Selector(text=html)
    title = (
        sel.css("h1.ui-pdp-title::text").get()
        or sel.css('meta[name="title"]::attr(content)').get()
        or sel.css("h1::text").get()
    )

    fraction_text = (
        sel.css(".andes-money-amount__fraction::text").get()
        or sel.css(".price-tag-fraction::text").get()
    )
    cents_text = (
        sel.css(".andes-money-amount__cents::text").get()
        or sel.css(".price-tag-decimal::text").get()
    )

    value: Optional[str] = None
    if fraction_text:
        whole_part = re.sub(r"\D", "", fraction_text)
        value = whole_part
        if cents_text:
            decimal_part = re.sub(r"\D", "", cents_text)
            value = f"{whole_part}.{decimal_part}"
    else:
        raw_price = (
            sel.css('span[itemprop="price"]::attr(content)').get()
            or sel.css('span[itemprop="price"]::text').get()
        )

        if raw_price:
            cleaned = re.sub(r"[^\d.,]", "", raw_price)
            if "," in cleaned and "." in cleaned:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", ".")
            value = cleaned or None

    currency_value = (
        sel.css('meta[itemprop="priceCurrency"]::attr(content)').get()
        or sel.css('meta[property="product:price:currency"]::attr(content)').get()
        or sel.css('meta[property="og:price:currency"]::attr(content)').get()
    )
    return {
        "name": title,
        "url": url,
        "current_price": _format_price(value, currency_value),
    }

def parse_amazon_html(html: str, url: str) -> dict:
    """ Extrai informações de produtos na Amazon Brasil """
    data = parse_generic_html(html, url)
    if data.get("name") and data.get("current_price"):
        return data
    sel = Selector(text=html)
    name = (
        sel.css("#productTitle::text").get()
        or sel.xpath(
            "//span[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'producttitle')]/text()"
        ).get()
        or sel.xpath(
            "//*[translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='title']/text()"
        ).get()
        or sel.css('meta[property="og:title"]::attr(content)').get()
    )

    raw_price = (
        sel.css("#corePriceDisplay_desktop_feature_div span.a-offscreen::text").get()
        or sel.css(".apexPriceToPay span.a-offscreen::text").get()
        or sel.css("#priceblock_ourprice::text").get()
        or sel.css("#priceblock_dealprice::text").get()
        or sel.css("#priceblock_saleprice::text").get()
        or sel.css("#price_inside_buybox::text").get()
        or sel.css("#apex_desktop span.a-price > span.a-offscreen::text").get()
    )

    currency: Optional[str] = sel.css('meta[property="og:price:currency"]::attr(content)').get()

    if not raw_price:
        whole = sel.css("span.a-price-whole::text").get()
        fraction = sel.css("span.a-price-fraction::text").get()
        if whole:
            whole_part = re.sub(r"\D", "", whole)
            fraction_part = re.sub(r"\D", "", fraction) if fraction else "00"
            raw_price = f"{whole_part}.{fraction_part}"
            if not currency:
                symbol = sel.css("span.a-price-symbol::text").get()
                currency = symbol.strip() if symbol else None

    if not currency and raw_price:
        symbol_match = re.match(r"[^\d]+", raw_price)
        currency = symbol_match.group(0).strip() if symbol_match else None

    numeric_price: Optional[str] = None
    if raw_price:
        cleaned = re.sub(r"[^\d.,]", "", raw_price)
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", ".")
        numeric_price = cleaned or None

    return {
        "name": name,
        "url": url,
        "current_price": _format_price(numeric_price, currency),
    }

def parse_magalu_html(html: str, url: str) -> dict:
    """ Coleta de dados das páginas de produtos de Magazine Luiza """
    data = parse_generic_html(html, url)
    if data.get("name") and data.get("current_price"):
        return data
    
    soup = BeautifulSoup(html, "lxml")
    name: Optional[str] = None
    price: Optional[str] = None

    script_tag = soup.find("script", string=re.compile("window.__INITIAL_STATE__"))
    if script_tag and script_tag.string:
        match = re.search(
            r"window.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
            script_tag.string,
            re.DOTALL,
        )
        if match:
            try:
                state = json.loads(match.group(1))

                def _deep_search(obj: Any, keys: set[str]):
                    """ Procura recursivamente por chaves relevantes no estado inicial """
                    normalized_keys = {key.lower() for key in keys}
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            lk = k.lower()
                            if lk in normalized_keys and not isinstance(v, (dict, list)):
                                return {lk: v}
                            found = _deep_search(v, keys)
                            if found:
                                return found
                    elif isinstance(obj, list):
                        for item in obj:
                            found = _deep_search(item, keys)
                            if found:
                                return found
                    return {}
                
                name_dict = _deep_search(state, {"name", "title"})
                price_dict = _deep_search(state, {"price", "pricevalue", "bestprice"})
                if name_dict:
                    name = next(iter(name_dict.values()))
                if price_dict:
                    price = next(iter(price_dict.values()))
            except json.JSONDecodeError:
                pass

    return {
        "name": name,
        "url": url,
        "current_price": _format_price(price, None),
    }


__all__ = [
    "parse_generic_html",
    "parse_meli_html",
    "parse_amazon_html",
    "parse_magalu_html",
]
