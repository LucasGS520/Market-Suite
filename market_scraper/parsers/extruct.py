from __future__ import annotations

""" Utilitários de parsing baseados em extruct

O módulo encapsula o uso da ``extruct`` para ler metadados estruturados
presentes no HTML de páginas de produtos. A interface exposta segue o 
padrão adotado no restante das estratégias do projeto, retornando um 
``dict`` com ``name``, ``current_price``, ``url`` e ``source`` quando
os dados obrigatórios são encontrados.

As funções aqui definidas priorizam JSON-LD, pois é a fonte mais comum
entre marketplaces modernos. Metadados OpenGraph são utilizados como
fallback apenas para complementar campos ausentes. Mantemos o tratamento
robusto para evitar exceções causadas por estruturas inesperadas e para
garantir que o preço retornado permaneça compatível com ``parse_price_str``.

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

import re
from collections.abc import Iterable
from typing import Any

from market_scraper.utils.extract_structured_data import extract_structured_data


STRUCTURED_DATA_SOURCE = "structured_data"

def _as_text(value: Any) -> str:
    """ Converte valores para string simples e enxutas """
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value}"
    return str(value).strip()

def _sanitize_price(value: str) -> str:
    """ Remove caracteres que atrapalhariam a interpretação do preço """
    cleaned = re.sub(r"[^0-9,.-]", "", value)
    return cleaned.strip()

def _first_item(sequence: Iterable[Any]) -> Any:
    """ Retorna o primeiro item de uma sequência """
    for item in sequence:
        if item:
            return item
    return None

def parse_with_extruct(html: str, url: str | None = None) -> dict[str, str] | None:
    """ Extrai nome e preço a partir dos dados estruturados presentes no HTML

    Parâmetros
    ----------
    html: str
        Conteúdo HTML bruto que contém scripts JSON-LD, Microdata ou OpenGraph
    url: str | None
        URL da página analisada. O valor é opcional, mas mantido na resposta para
        padronizar a interface entre os parsers.

    Retorno
    -------
    dict[str, str]
        Dicionário padronizado com ``name``, ``current_price``, ``url`` e ``source``.
        Quando os dados obrigatórios não são encontrados, retorna ``None``.
    """
    data = extract_structured_data(html, url) or {}

    name: str = ""
    price: str = ""

    json_ld_items = data.get("json-ld") or []
    if not isinstance(json_ld_items, Iterable) or isinstance(json_ld_items, (str, bytes)):
        json_ld_items = [json_ld_items]

    for item in json_ld_items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("@type")
        if isinstance(item_type, list):
            match = _first_item(type_name for type_name in item_type if type_name in {"Product", "Offer"})
            if not match:
                continue
        elif item_type not in {"Product", "Offer"}:
            continue
        name_candidate = _as_text(item.get("name"))
        if name_candidate:
            name = name_candidate
        offers = item.get("offers")
        if isinstance(offers, dict):
            raw_price = _as_text(offers.get("price") or offers.get("lowPrice"))
            if raw_price:
                price = _sanitize_price(raw_price)
        elif isinstance(offers, list):
            first_offer = next((offer for offer in offers if isinstance(offer, dict)), None)
            if first_offer:
                raw_price = _as_text(first_offer.get("price") or first_offer.get("lowPrice"))
                if raw_price:
                    price = _sanitize_price(raw_price)
        if not price:
            raw_price = _as_text(item.get("price"))
            if raw_price:
                price = _sanitize_price(raw_price)
        if name and price:
            break

    if not name or not price:
        opengraph = data.get("opengraph") or []
        if isinstance(opengraph, list):
            og_map: dict[str, Any] = {}
            for entry in opengraph:
                if not isinstance(entry, dict):
                    continue
                if "property" in entry and "content" in entry:
                    og_map[entry.get("property")] = entry.get("content")
                else:
                    for key, value in entry.items():
                        if isinstance(key, str) and value is not None:
                            og_map.setdefault(key, value)
            if not name:
                name = _as_text(og_map.get("og:title"))
            if not price:
                price = _sanitize_price(_as_text(og_map.get("product:price:amount")))

    if not name or not price:
        return None

    return {
        "name": name,
        "current_price": price,
        "url": url or "",
        "source": STRUCTURED_DATA_SOURCE,
    }


__all__ = ["parse_with_extruct"]
