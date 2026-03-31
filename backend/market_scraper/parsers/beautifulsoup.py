""" Funções de parsing utilizando BeautifulSoup

O objetivo do módulo é oferecer um ponto único para extração simples
de nome e preço a partir de HTML estático. Ele funciona como complemento
ao ``html_static.py`` e mantém a mesma interface das demais bibliotecas
de parsing utilizadas no projeto. As saídas são preparadas para que o 
``DataQualityValidator`` consiga interpretar os valores sem ambiguidades.

Exemplo
-------
>>> html = '''
... <html><head><title>Notebook ABC</title></head>
... <body><span class='price'>R$ 5.999,90</span></body></html>
... '''
>>> parse_with_beautifulsoup(html, url="https://loja.test/notebook")
{'name': 'Notebook ABC', 'current_price': 'R$ 5.999,90', 'url': 'https://loja.test/notebook'}
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

HTML_METADATA_SOURCE = "html_metadata"

_NAME_SELECTORS = [
    ("meta", {"property": "og:title"}),
    ("meta", {"name": "title"}),
    ("meta", {"name": "twitter:title"}),
    ("meta", {"property": "twitter:title"}),
    ("meta", {"itemprop": "name"}),
    ("meta", {"name": "parsely-title"}),
    ("span", {"id": "productTitle"}),
    ("h1", {"class": "ui-pdp-title"}),
    ("h1", {"data-testid": "heading-product-title"}),
    ("span", {"data-testid": "heading-product-title"}),
    ("h1", {}),
    ("title", {}),
]

#Mantemos os seletores organizados por prioridade para cobrir variações comuns dos marketplaces sem depender de heurísticas fragéis
_PRICE_SELECTORS = [
    ("meta", {"itemprop": "price"}),
    ("meta", {"property": "product:price:amount"}),
    ("meta", {"property": "og:price:amount"}),
    ("meta", {"name": "twitter:data1"}),
    ("meta", {"itemprop": "priceCurrency"}),
    ("span", {"id": "price_inside_buybox"}),
    ("span", {"id": "priceblock_ourprice"}),
    ("span", {"id": "priceblock_dealprice"}),
    ("span", {"class": "a-offscreen"}),
    ("span", {"class": "a-price-whole"}),
    ("span", {"class": "a-price-range"}),
    ("span", {"class": "andes-money-amount__fraction"}),
    ("span", {"class": "andes-money-amount__fraction_2"}),
    ("span", {"class": "price-tag-fraction"}),
    ("span", {"class": "ui-pdp-price__second-line"}),
    ("span", {"data-testid": "price-value"}),
    ("span", {"data-testid": "price-amount"}),
    ("div", {"class": "price"}),
    ("span", {"class": "price"}),
    ("span", {"data-price": True}),
    ("span", {"data-value": True}),
    ("data", {"itemprop": "price"}),
]

#Seletores auxiliares capturam centavos exibidos separados em páginas de produto
_FRACTION_SELECTORS = [
    ("span", {"class": "andes-money-amount__cents"}),
    ("span", {"class": "price-tag-decimal"}),
    ("span", {"data-testid": "price-decimal"}),
]

def _clean_text(value: str | None) -> str:
    """ Normaliza strings removendo espaços extras """
    return value.strip() if value else ""

def _clean_price_text(value: str | None) -> str:
    """ Remove símbolos extras mantendo apenas números, vírgulas e pontos """
    if not value:
        return ""
    cleaned = re.sub(r"[^0-9,.-]", "", value)
    return cleaned.strip()

def parse_with_beautifulsoup(html: str, url: str | None = None) -> dict[str, str] | None:
    """ Extrai nome e preço utilizando `BeautifulSoup`
    
    Parâmetros
    ----------
    html: str
        Conteúdo HTML da página em formato de string
    url: str | None
        Endereço da página, mantido na resposta para padronizar a interface

    Retorna
    -------
    dict[str, str]
        Dicionário com os campos ``name``, ``current_price``, ``url`` e ``source``
        ou ``None`` quando os valores obrigatórios estão ausentes.
    """
    soup = BeautifulSoup(html, "lxml")

    name = ""
    for tag, attrs in _NAME_SELECTORS:
        element = soup.find(tag, attrs=attrs)
        if not element:
            continue
        if element.name == "meta":
            name = _clean_text(element.get("content"))
        else:
            name = _clean_text(element.get_text())
        if name:
            break

    price = ""
    for tag, attrs in _PRICE_SELECTORS:
        element = soup.find(tag, attrs=attrs)
        if not element:
            continue
        if element.name == "meta":
            price = _clean_price_text(element.get("content"))
        elif element.name == "data":
            price = _clean_price_text(element.get("value"))
        else:
            price = _clean_price_text(element.get_text())
        if price:
            break

    if price and price.isdigit():
        for tag, attrs in _FRACTION_SELECTORS:
            fraction_element = soup.find(tag, attrs=attrs)
            if not fraction_element:
                continue
            fraction_digits = re.sub(r"\D", "", fraction_element.get_text() or "")
            if not fraction_digits:
                continue
            price = f"{price}.{fraction_digits}"
            break

    if not name or not price:
        return None

    canonical_url = ""
    
    def _is_canonical(value: str | list[str] | None) -> bool:
        """ Avalia se o atributo ``rel`` referencia o link canônico """
        if value is None:
            return False
        if isinstance(value, list):
            return any(item.lower() == "canonical" for item in value if isinstance(item, str))
        return value.lower() == "canonical"

    canonical_tag = soup.find("link", rel=_is_canonical)
    if canonical_tag:
        href = canonical_tag.get("href")
        if href:
            canonical_url = href.strip() 

    return {
        "name": name,
        "current_price": price,
        "url": canonical_url or (url or ""),
        "source": HTML_METADATA_SOURCE,
    }


__all__ = ["parse_with_beautifulsoup"]
