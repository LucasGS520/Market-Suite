""" Funções auxiliares para extração de dados estruturados com Extruct 

O módulo continua privilegiando a biblioteca ``extruct`` para recuperar
metadados como JSON-LD, Microdata e OpenGraph, mas agora conta com um
fallback baseado em ``selectolax`` para lidar com páginas que não são
interpretadas corretamente pela primeira estratégia. A API públcia
da função permanece inalterada para manter compatibilidade com o pipeline.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any, Dict, Optional

import extruct
import structlog
from selectolax.parser import HTMLParser
from w3lib.html import get_base_url

from shared.utils.logging_utils import sanitize_log_data


#Logger estruturado para capturar erros de parsing com extruct e fallback
logger = structlog.get_logger(__name__)

def _empty_payload() -> Dict[str, list[Any]]:
    """ Cria o dicionário padrão com listas vazias independentes """
    return {"json-ld": [], "microdata": [], "opengraph": []}

def _has_payload(data: Dict[str, Any]) -> bool:
    """ Verifica se o dicionário retornado contém ao menos um valor útil """
    return any(bool(data.get(key)) for key in ("json-ld", "microdata", "opengraph"))

def _extract_with_selectolax(html: str) -> Dict[str, Any]:
    """ Aplica heurísticas leves com selectolax para recuperar metadados 
    
    A função mantém a mesma estrutura esperada pelo pipeline, populando as 
    chaves ``json-ld``, ``microdata`` e ``opengraph`` quando encontrar 
    conteúdo relevante. Quando nenhuma informação é identificada, devolve
    o dicionário padronizado com listas vazias, sinalizando que os fallbacks
    subsequentes ainda podem ser acionados.
    """
    parser = HTMLParser(html)
    json_ld_payload: list[Any] = []
    for node in parser.css("script[type='application/ld+json']"):
        #Utilizamos ``deep=True`` para respeitar quebras de linha internas, sem percas de trechos relevantes do JSON-LD original
        content = node.text(deep=True).strip()
        if not content:
            continue
        try:
            json_ld_payload.append(json.loads(content))
        except (JSONDecodeError, TypeError):
            #Ignora blocos inválidos, geralmente representam scripts mistos que não resepeitam formato JSON-LD
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
    for meta in parser.css("meta[property^='og:']"):
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

def extract_structured_data(html: str, url: Optional[str] = None) -> Dict[str, Any]:
    """ Extrai metadados estruturados presentes no HTML informado 
    
    Parâmetros:
        html: Conteúdo HTML bruto obtido do site.
        url: URL da página, utilizada como base para resolver caminhos
            relativos. O valor é opcional, mas recomendado para resultados
            mais precisos.

    Retorna:
        Dicionário com os dados estruturados detectados, preferencialmente
        pela biblioteca ``extruct``. Quando não há resultado, ativa o
        fallback baseado em ``selectolax`` antes de devolver as listas
        vazias esperadas pelas etapas seguintes do pipeline.
    """
    base_url = get_base_url(html, url)
    try:
        result = extruct.extract(
            html,
            base_url=base_url,
            syntaxes=["json-ld", "microdata", "opengraph"],
            uniform=True,
        )
        if _has_payload(result):
            return result
        fallback_result = _extract_with_selectolax(html)
        return fallback_result
    except (JSONDecodeError, ValueError) as exc:
        logger.exception(
            "erro_extracao_dados_estruturados",
            error=sanitize_log_data(str(exc)),
        )
        fallback_result = _extract_with_selectolax(html)
        if _has_payload(fallback_result):
            return fallback_result
        return _empty_payload()
