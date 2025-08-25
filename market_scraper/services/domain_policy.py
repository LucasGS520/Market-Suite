from __future__ import annotations

""" Política de seleção de estratégias por domínio

Este módulo define a ordem de execução das estratégias de scraping para
cada marketplace suportado. Novas estratégias podem ser registradas no
mapa ``STRATEGY_REGISTRY`` e referenciadas em ``DOMAIN_POLICES``
"""

from typing import Dict, List, Type
from urllib.parse import urlparse

from market_scraper.strategies import ScrapingStrategy, PlaywrightDefaultStrategy


#Registro de estratégias disponíveis no sistema.
#O valor corresponde á classe responsável por executar a coleta.
#Novas implementações devem ser adicionadas aqui:
STRATEGY_REGISTRY: Dict[str, Type[ScrapingStrategy]] = {
    "PLAYWRIGHT": PlaywrightDefaultStrategy,
    # "HTML": HtmlStrategy, #Exemplos para expansões
    # "JSON": JsonStrategy,
}

#Mapeamento entre domínio e a ordem preferencial de estratégias
#As chaves correspondem aos domínios oficiais de cada marketplace
#Estratégias não registradas em ``STRATEGY_REGISTRY`` são ignoradas
DOMAIN_POLICIES: Dict[str, List[str]] = {
    "shopee.com": ["JSON", "HTML", "PLAYWRIGHT"],
    "magazineluiza.com.br": ["HTML", "PLAYWRIGHT"],
    "mercadolivre.com.br": ["HTML", "PLAYWRIGHT"],
}

def _extract_host(url: str) -> str:
    """ Extrai o host de uma URL normalizando para minúsculas

    O parâmetro ``url`` pode ser qualquer objeto convertível
    para ``str``, como tipos provenientes do Pydantic.
    """
    return urlparse(str(url)).netloc.lower()

def strategies_for(url: str) -> List[ScrapingStrategy]:
    """ Retorna instâncias de estratégias ordenadas para o domínio

    Caso não exista configuração específica para o domínio, a
    estratégia padrão é utilizada (No momento é Playwright, mas ao decorrer do projeto pode ser alterado).
    """
    host = _extract_host(url)
    for domain, names in DOMAIN_POLICIES.items():
        if domain in host:
            return [STRATEGY_REGISTRY[name]() for name in names if name in STRATEGY_REGISTRY]
    #Fallback para a estratégia padrão
    return [PlaywrightDefaultStrategy()]
