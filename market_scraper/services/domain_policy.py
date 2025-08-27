from __future__ import annotations

""" Política de seleção de estratégias por domínio

Este módulo define a ordem de execução das estratégias de scraping para
cada marketplace suportado. Novas estratégias podem ser registradas no
mapa ``STRATEGY_REGISTRY`` e referenciadas em ``DOMAIN_POLICIES``
"""

from typing import Dict, List, Type

from market_scraper.strategies import (
    ScrapingStrategy,
    PlaywrightDefaultStrategy,
    MercadoLivreHtmlStaticStrategy,
    AmazonHtmlStaticStrategy,
    ShopeeHtmlStaticStrategy,
    MagaluHtmlStaticStrategy,
)
from market_scraper.utils.http_utils import extract_hostname


#Registro de estratégias disponíveis no sistema.
#O valor corresponde à classe responsável por executar a coleta.
#Novas implementações devem ser adicionadas aqui:
STRATEGY_REGISTRY: Dict[str, Type[ScrapingStrategy]] = {
    "PLAYWRIGHT": PlaywrightDefaultStrategy,
    "HTML_ML": MercadoLivreHtmlStaticStrategy,
    "HTML_AMAZON": AmazonHtmlStaticStrategy,
    "HTML_SHOPEE": ShopeeHtmlStaticStrategy,
    "HTML_MAGALU": MagaluHtmlStaticStrategy,
}

#Mapeamento entre domínio e a ordem preferencial de estratégias
#As chaves correspondem aos domínios oficiais de cada marketplace
#Estratégias não registradas em ``STRATEGY_REGISTRY`` são ignoradas
DOMAIN_POLICIES: Dict[str, List[str]] = {
    "mercadolivre.com.br": ["HTML_ML", "PLAYWRIGHT"],
    "amazon.com.br": ["HTML_AMAZON","PLAYWRIGHT"],
    "shopee.com": ["HTML_SHOPEE", "PLAYWRIGHT"],
    "magazineluiza.com.br": ["HTML_MAGALU", "PLAYWRIGHT"],
}


def strategies_for(url: str) -> List[ScrapingStrategy]:
    """ Retorna instâncias de estratégias ordenadas para o domínio

    A função utiliza :func:`extract_hostname` para obter o host da URL e,
    com base nele, seleciona a ordem preferencial de estratégias. Caso o
    domínio não esteja configurado, a estratégia padrão é retornada.
    """
    host = extract_hostname(url)
    for domain, names in DOMAIN_POLICIES.items():
        if domain in host:
            return [STRATEGY_REGISTRY[name]() for name in names if name in STRATEGY_REGISTRY]
    #Fallback para a estratégia padrão
    return [PlaywrightDefaultStrategy()]
