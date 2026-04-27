""" Funções auxiliares para extração de dados estruturados via Extruct

O módulo usa a biblioteca ``extruct`` como caminho principal para JSON-LD,
Microdata e OpenGraph. Um fallback local com ``selectolax`` permanece para
preservar robustez quando a dependência externa falhar em runtime.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any, Dict, Optional

import structlog
from selectolax.parser import HTMLParser

from shared.utils.logging_utils import sanitize_log_data

try:
    from extruct import extract as _extruct_extract
except ImportError:
    _extruct_extract = None


logger = structlog.get_logger(__name__)

def _empty_payload() -> Dict[str, list[Any]]:
    """ Cria o dicionário padrão com listas vazias independentes """
    return {"json-ld": [], "microdata": [], "opengraph": []}

def extract_structured_data(html: str, _url: Optional[str] = None) -> Dict[str, Any]:
    """ Extrai metadados estruturados presentes no HTML informado

    Parâmetros:
        html: Conteúdo HTML bruto obtido do site.
        url: URL da página (mantido para compatibilidade de assinatura, não utilizado).

    Retorna:
        Dicionário com as chaves ``json-ld``, ``microdata`` e ``opengraph``,
        cada uma contendo uma lista de itens encontrados. Quando nenhum
        conteúdo é identificado, devolve listas vazias.
    """
    if _extruct_extract is not None:
        try:
            data = _extruct_extract(
                html,
                base_url=_url,
                syntaxes=["json-ld", "microdata", "opengraph"],
                uniform=False,
            )
            return {
                "json-ld": data.get("json-ld") or [],
                "microdata": data.get("microdata") or [],
                "opengraph": data.get("opengraph") or [],
            }
        except Exception as exc:
            logger.warning(
                "erro_extracao_extruct",
                error=sanitize_log_data(str(exc)),
            )

    try:
        parser = HTMLParser(html)

        json_ld_payload: list[Any] = []
        for node in parser.css("script[type='application/ld+json']"):
            content = node.text(deep=True).strip()
            if not content:
                continue
            try:
                json_ld_payload.append(json.loads(content))
            except (JSONDecodeError, TypeError):
                continue

        microdata_payload: list[Dict[str, Any]] = []
        for node in parser.css("[itemscope][itemtype]"):
            item: Dict[str, Any] = {"@type": node.attributes.get("itemtype", "")}
            properties: Dict[str, Any] = {}
            for prop in node.css("[itemprop]"):
                prop_name = prop.attributes.get("itemprop")
                if not prop_name:
                    continue
                prop_value = prop.attributes.get("content") or prop.text(strip=True)
                if prop_value:
                    properties[prop_name] = prop_value
            if properties:
                item["properties"] = properties
                microdata_payload.append(item)

        opengraph_payload: list[Dict[str, str]] = []
        # Captura og:*, product:* e twitter:* — os três namespaces lidos pelo pipeline
        for meta in parser.css("meta[property^='og:'], meta[property^='product:'], meta[property^='twitter:']"):
            property_name = meta.attributes.get("property")
            content = meta.attributes.get("content")
            if property_name and content:
                opengraph_payload.append({property_name: content})

        if json_ld_payload or microdata_payload or opengraph_payload:
            return {
                "json-ld": json_ld_payload,
                "microdata": microdata_payload,
                "opengraph": opengraph_payload,
            }
        return _empty_payload()

    except Exception as exc:
        logger.warning(
            "erro_extracao_dados_estruturados",
            error=sanitize_log_data(str(exc)),
        )
        return _empty_payload()
