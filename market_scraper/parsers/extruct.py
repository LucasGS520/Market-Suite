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
from typing import Any, Iterator

from market_scraper.utils.extract_structured_data import extract_structured_data


STRUCTURED_DATA_SOURCE = "structured_data"

def _iter_json_ld_items(raw_items: Iterable[Any]) -> Iterator[dict[str, Any]]:
    """ Expande listas e grafos do JSON-LD para alcançar todos os nós úteis """
    for item in raw_items:
        if isinstance(item, dict):
            graph = item.get("@graph")
            if isinstance(graph, list):
                for graph_item in graph:
                    if isinstance(graph_item, dict):
                        yield graph_item
                continue
            yield item
        elif isinstance(item, Iterable) and not isinstance(item, (str, bytes)):
            for entry in item:
                if isinstance(entry, dict):
                    yield entry

def _extract_price_from_offers(candidate: Any) -> str:
    """ Percorre variações de ``offers`` buscando um valor monetário confiável """
    def _iter_offers(value: Any) -> Iterator[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            nested = value.get("offers")
            if nested is not None and nested is not value:
                yield from _iter_offers(nested)
            price_spec = value.get("priceSpecification")
            if isinstance(price_spec, list):
                for spec in price_spec:
                    if isinstance(spec, dict):
                        yield spec
            elif isinstance(price_spec, dict):
                yield price_spec
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            for entry in value:
                yield from _iter_offers(entry)
    
    for offer in _iter_offers(candidate):
        for key in ("price", "lowPrice", "highPrice", "amount", "priceAmount", "priceValue"):
            raw_value = _as_text(offer.get(key))
            if raw_value:
                return _sanitize_price(raw_value)
    return ""

def _extract_name_from_item(item: dict[str, Any]) -> str:
    """ Normaliza os campos candidatos a nome do produto """
    name_candidate = _as_text(item.get("name"))
    if name_candidate:
        return name_candidate
    
    #Algumas páginas expõem ``itemOffered`` ou ``mainEntity`` contendo o nome real
    for key in ("itemOffered", "mainEntity"):
        nested = item.get(key)
        if isinstance(nested, dict):
            nested_name = _as_text(nested.get("name"))
            if nested_name:
                return nested_name
    brand = item.get("brand")
    if isinstance(brand, dict):
        brand_name = _as_text(brand.get("name"))
        if brand_name:
            return brand_name
    return ""

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

    for item in _iter_json_ld_items(json_ld_items):
        item_type = item.get("@type")
        if isinstance(item_type, list):
            match = _first_item(type_name for type_name in item_type if type_name in {"Product", "Offer"})
            if not match:
                continue
        elif item_type not in {"Product", "Offer"}:
            continue
        name_candidate = _extract_name_from_item(item)
        if name_candidate:
            name = name_candidate
        offers = item.get("offers")
        if offers:
            price_candidate = _extract_price_from_offers(offers)
            if price_candidate:
                price = price_candidate
        if not price:
            raw_price = _extract_price_from_offers(item)
            if raw_price:
                price = raw_price
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
