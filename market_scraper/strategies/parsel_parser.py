from __future__ import annotations

""" Funções auxiliares para parsing com Parsel

A biblioteca ``Parsel`` oferece recursos poderosos de seleção via XPath
ou CSS. Este módulo disponibliza uma função única para extrair nome e preço
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

import json
from parsel import Selector


def parse_with_parsel(html: str, url: str | None = None) -> dict[str, str]:
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
        Dicionário padronizado com ``name``, ``current_price`` e ``url``
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
                name = str(data.get("name") or "").strip() or name
                offers = data.get("offers")
                if isinstance(offers, dict):
                    price = str(offers.get("price") or offers.get("lowPrice") or "").strip() or price
                elif isinstance(offers, list):
                    first_offer = next((offer for offer in offers if isinstance(offer, dict)), {})
                    price = str(first_offer.get("price") or first_offer.get("lowPrice") or "").strip() or price
                price = price or str(data.get("price") or "").strip()
        except json.JSONDecodeError:
            pass

    if not name:
        name = selector.css("meta[property='og:title']::attr(content)").get(default="")
    if not name:
        name = selector.css("title::text").get(default="")

    if not price:
        price = selector.css("meta[itemprop='price']::attr(content)").get(default="")
    if not price:
        price = selector.css("span#price::text").get(default="")
    if not price:
        price = selector.css("span.price::text").get(default="")

    return {
        "name": name.strip(),
        "current_price": price.strip(),
        "url": url or "",
    }

__all__ = ["parse_with_parsel"]
