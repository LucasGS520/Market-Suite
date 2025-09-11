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


def extract_structured_data(html: str, url: Optional[str] = None) -> Dict[str, Any]:
    """ EXtrai metadados estruturados presentes no HTML informado 
    
    Parâmetros:
        html: Conteúdo HTML bruto obtido do site
        url: URL da página, utilizada como base para resolver caminhos relativos.
        O valor é opcional, mas recomendado para resultados mais precisos.

    Retorna:
        Dicionário com os dados estruturados detectados pela biblioteca ``extruct``.
        As chaves mais comuns são ``json-ld``, ``microdata`` e ``opengraph``.
    """
    base_url = get_base_url(html, url)
    return extruct.extract(
        html,
        base_url=base_url,
        syntaxes=["json-ld", "microdata", "opengraph"],
        uniform=True,
    )
