from __future__ import annotations

""" Utilitários de parsing baseados em extruct

O módulo encapsula o uso da ``extruct`` para ler metadados estruturados
presentes no HTML de páginas de produtos. A interface exposta segue o 
padrão adotado no restante das estratégias do projeto, retornando um 
``dict`` com ``name``, ``current_price`` e ``url``.

Exemplo
-------
>>> html = '''
... <html><head>
... <script type='application/ld+json'>
... {"@type": "Product", "name": "Câmera", "offers": {"price": "3500.00"}}
... </script>
... </head></html>
... '''
>>> parse_with_extruct(html, url="https://exemplo.com/produto")
{'name': 'Câmera', 'current_price': '3500.00', 'url': 'https://exemplo.com/produto'}
"""

from collections.abc import Iterable
from typing import Any

from market_scraper.utils.extract_structured_data import extract_structured_data


def _as_text(value: Any) -> str:
    """ Converte valores para string simples"""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value}"
    return str(value).strip()

def _first_item(sequence: Iterable[Any]) -> Any:
    """ Retorna o primeiro item de uma sequência """
    for item in sequence:
        if item:
            return item
    return None

def parse_with_extruct(html: str, url: str | None = None) -> dict[str, str]:
    """ Extrai nome e preço a partir dos dados estruturados presentes no HTML
    
    Parêmetros
    ----------
    html: str
        Conteúdo HTML bruto que contém scripts JSON-LD, Microdata ou OpenGraph
    url: str | None
        URL da página analisada. O valor é opcional, mas mantido na resposta para
        padronizar a interface entre os parsers.

    Retorno
    -------
    dict[str, str]
        Dicionário padronizado com ``name``, ``current_price`` e ``url``
        Caso nenhuma informação seja encontrada, valores vazios são retornados.
    """
    data = extract_structured_data(html, url)

    name: str = ""
    price: str = ""

    for item in data.get("json-ld", []):
        if not isinstance(item, dict):
            continue
        item_type = item.get("@type")
        if isinstance(item_type, list):
            match = _first_item(type_name for type_name in item_type if type_name in {"Product", "Offer"})
            if not match:
                continue
        elif item_type not in {"Product", "Offer"}:
            continue
        name = _as_text(item.get("name")) or name
        offers = item.get("offers")
        if isinstance(offers, dict):
            price = _as_text(offers.get("price") or offers.get("lowPrice"))
        elif isinstance(offers, list):
            firsrt_offer = next((offer for offer in offers if isinstance(offer, dict)), None)
            if firsrt_offer:
                price = _as_text(firsrt_offer.get("price") or firsrt_offer.get("lowPrice"))
        price = price or _as_text(item.get("price"))
        if name and price:
            break

    if not name or not price:
        opengraph = data.get("opengraph") or []
        if isinstance(opengraph, list):
            og_map = {
                entry.get("property"): entry.get("content")
                for entry in opengraph
                if isinstance(entry, dict)
            }
            name = name or _as_text(og_map.get("og:title"))
            price = price or _as_text(og_map.get("product:price:amount"))

    return {
        "name": name, 
        "current_price": price,
        "url": url or "",
    }

__all__ = ["parse_with_extruct"]
