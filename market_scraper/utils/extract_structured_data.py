""" Funções auxiliares para extração de dados estruturados com Extruct 

Este módulo centraliza a utilização da biblioteca ``extruct`` para
recuperar metadados como JSON-LD, Microdata e Open Graph a partir de 
um HTML bruto. Ao padronizar essa etapa em uma função única, 
facilitamos a manutenção e garantimos comportamento consistente entre
as estratégias de scraping.
"""

from typing import Any, Dict, Optional

import extruct
from w3lib.html import get_base_url
from json import JSONDecodeError
from time import perf_counter
import structlog

from shared.metrics.metrics_parser import PARSER_FAILURE_TOTAL, PARSER_SUCCESS_TOTAL, PARSER_DURATION_SECONDS
from shared.utils.logging_utils import sanitize_log_data

#Logger extruturado para capturar erros de parsing com extruct
logger = structlog.get_logger(__name__)


def extract_structured_data(html: str, url: Optional[str] = None) -> Dict[str, Any]:
    """ EXtrai metadados estruturados presentes no HTML informado 
    
    Parâmetros:
        html: Conteúdo HTML bruto obtido do site
        url: URL da página, utilizada como base para resolver caminhos relativos.
            O valor é opcional, mas recomendado para resultados mais precisos.

    Retorna:
        Dicionário com os dados estruturados detectados pela biblioteca ``extruct``.
        As chaves mais comuns são ``json-ld``, ``microdata`` e ``opengraph``.
        Em caso de erro de parsing, retorna um dicionário vazio para permitir que a estratégia realize o fallback adequado
    """
    base_url = get_base_url(html, url)
    home = perf_counter()
    try:
        result = extruct.extract(
            html,
            base_url=base_url,
            syntaxes=["json-ld", "microdata", "opengraph"],
            uniform=True,
        )
        PARSER_SUCCESS_TOTAL.labels(library="extruct").inc()
        return result
    except (JSONDecodeError, ValueError) as exc:
        PARSER_FAILURE_TOTAL.labels(library="extruct").inc()
        logger.exception("Erro ao extrair dados estruturados com Extruct", erro=sanitize_log_data(str(exc)))
        #Retorna um dicionário com listas vazias para sinalizar ausência de dados válidos sem interromper o fluxo das estratégias
        return {"json-ld": [], "microdata": [], "opengraph": []}
    finally:
        duration = perf_counter() - home
        PARSER_DURATION_SECONDS.labels(library="extruct").observe(duration)
