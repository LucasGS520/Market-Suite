""" Funções auxiliares para parsing com Parsel

A biblioteca ``Parsel`` oferece recursos poderosos de seleção via XPath
ou CSS. Este módulo disponibliza uma funções para extrair nome e preço
de páginas HTML utilizando esses seletores.

Exemplo
-------
>>> html = '''
... <html><head><meta property='og:title' content='Console XYZ' />
... <script type='application/ld+json'>
... {"@type": "Product", "name": "Console XYZ", "offers": {"price": "2999.00"}}
... </script></head><body></body></html>
... '''
>>> parse_with_parsel(html, url="https://loja.test/produto")
{'name': 'Console XYZ', 'current_price': '2999.00', 'url': 'https://loja.test/produto'}
"""

from __future__ import annotations

import json
import re
from typing import Optional

from parsel import Selector

PARSEL_SOURCE = "parsel"

def _clean_text(value: Optional[str]) -> str:
    """ Remove espaços extras mantendo o texto relevante """
    return value.strip() if value else ""

def _sanitize_price(value: Optional[str]) -> str:
    """ Remove símbolos que atrapalham a validação do preço """
    if not value:
        return ""
    return re.sub(r"[^0-9,.-]", "", value).strip()

def _combine_price_parts(integer: str, fraction: str) -> str:
    """ Monta uma string decimal a partir de partes separadas """
    if not integer:
        return ""
    digits = re.sub(r"\D", "", integer)
    decimals = re.sub(r"\D", "", fraction)
    if not digits:
        return ""
    if decimals:
        return f"{digits}.{decimals}"
    return digits

def parse_with_parsel(html: str, url: str | None = None) -> dict[str, str] | None:
    """ Realiza a extração de campos básicos utilizando a ``Parsel``

    Parâmetros
    ----------
    html: str
        Documento HTML bruto será analisado
    url: str | None
        URL da página. A informação é opcional e retorna vazia quando não fornecida,
        mantendo a consistência da interface dos parsers.

    Retorna
    -------
    dict[str, str]
        Dicionário padronizado com ``name``, ``current_price``, ``url`` e ``source``
        ou ``None`` quando os dados obrigatórios não são encontrados.
    """
    selector = Selector(text=html)

    name = ""
    price = ""

    json_ld = selector.xpath("string(//script[@type='application/ld+json'][1])").get()
    if json_ld:
        try:
            data = json.loads(json_ld)
            if isinstance(data, list):
                data = next((item for item in data if isinstance(item, dict)), {})
            if isinstance(data, dict):
                name = _clean_text(str(data.get("name") or "")) or name
                offers = data.get("offers")
                if isinstance(offers, dict):
                    price = _sanitize_price(str(offers.get("price") or offers.get("lowPrice") or "")) or price
                elif isinstance(offers, list):
                    first_offer = next((offer for offer in offers if isinstance(offer, dict)), {})
                    price = _sanitize_price(str(first_offer.get("price") or first_offer.get("lowPrice") or "")) or price
                price = price or _sanitize_price(str(data.get("price") or ""))
        except json.JSONDecodeError:
            pass

    if not name:
        name = _clean_text(selector.css("meta[name='twitter:title']::attr(content)").get(default=""))
    if not name:
        name = _clean_text(selector.css("meta[property='og:title']::attr(content)").get(default=""))
    if not name:
        name = _clean_text(selector.css("meta[name='title']::attr(content)").get(default=""))
    if not name:
        name = _clean_text(selector.css("meta[property='twitter:title']::attr(content)").get(default=""))
    if not name:
        name = _clean_text(selector.css("span#productTitle::text").get(default=""))
    if not name:
        name = _clean_text(selector.css("h1::text").get(default=""))
    if not name:
        name = _clean_text(selector.css("title::text").get(default=""))

    if not price:
        price = _sanitize_price(selector.css("meta[itemprop='price']::attr(content)").get(default=""))
    if not price:
        price = _sanitize_price(selector.css("meta[property='product:price:amount']::attr(content)").get(default=""))
    if not price:
        price = _sanitize_price(selector.css("meta[name='twitter:data1']::attr(content)").get(default=""))
    if not price:
        price = _sanitize_price(
            selector.css("#price_inside_buybox::text").get(default="")
            or selector.css("#corePriceDisplay_desktop_feature_div span.a-offscreen::text").get(default="")
            or selector.css(".a-price span.a-offscreen::text").get(default="")
        )
    if not price:
        combined = _combine_price_parts(
            selector.css("span[data-testid='price-integer']::text").get(default=""),
            selector.css("span[data-testid='price-decimal']::text").get(default=""),
        )
        price = combined or price
    if not price:
        price = _sanitize_price(selector.css("span.price::text").get(default=""))

    canonical_url = _clean_text(selector.css("link[rel='canonical']::attr(href)").get(default=""))
    #Mantemos o canonical como referência sempre que disponível para preservar a origem real do produto
    normalized_url = canonical_url or (url or "")

    name = _clean_text(name)
    price = _sanitize_price(price)
    price = price.strip()
    if not name or not price:
        return None

    return {
        "name": name,
        "current_price": price,
        "url": normalized_url,
        "source": PARSEL_SOURCE,
    }


__all__ = ["parse_with_parsel"]
