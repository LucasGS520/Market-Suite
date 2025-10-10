from __future__ import annotations

""" Funções de parsing utilizando BeautifulSoup

O objetivo do módulo é oferecer um ponto único para extração simples
de nome e preço a partir de HTML estático. Ele funcionna como complemento
ao ``html_static.py`` e matém a mesma interface das demais bibliotecas
de parsing utilizadas no projeto. As saídas são preparadas para que o 
``DataQualityValidator`` consiga interpretar os valores sem ambuiguidades.

Exemplo
-------
>>> html = '''
... <html><head><title>Notebook ABC</title></head>
... <body><span class='price'>R$ 5.999,90</span></body></html>
... '''
>>> parse_with_beautifulsoup(html, url="https://loja.test/notebook")
{'name': 'Notebook ABC', 'current_price': 'R$ 5.999,90', 'url': 'https://loja.test/notebook'}
"""

import re

from bs4 import BeautifulSoup

HTML_METADATA_SOURCE = "html_metadata"

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

    name_candidates = [
        ("meta", {"property": "og:title"}),
        ("meta", {"name": "title"}),
        ("h1", {}),
        ("title", {}),
    ]
    name = ""
    for tag, attrs in name_candidates:
        element = soup.find(tag, attrs=attrs)
        if not element:
            continue
        if element.name == "meta":
            name = _clean_text(element.get("content"))
        else:
            name = _clean_text(element.get_text())
        if name:
            break

    price_selectors = [
        ("meta", {"itemprop": "price"}),
        ("meta", {"property": "product:price:amount"}),
        ("span", {"id": "price"}),
        ("span", {"class": "price"}),
        ("div", {"class": "price"}),
    ]
    price = ""
    for tag, attrs in price_selectors:
        element = soup.find(tag, attrs=attrs)
        if not element:
            continue
        if element.name == "meta":
            price = _clean_price_text(element.get("content"))
        else:
            price = _clean_price_text(element.get_text())
        if price:
            break

    if not name or not price:
        return None

    return {
        "name": name,
        "current_price": price,
        "url": url or "",
        "source": HTML_METADATA_SOURCE,
    }


__all__ = ["parse_with_beautifulsoup"]
