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
    MercadoLivreJsonStrategy,
    AmazonJsonStrategy,
    ShopeeJsonStrategy,
    MagaluJsonStrategy,
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
    "JSON_ML": MercadoLivreJsonStrategy,
    "JSON_AMAZON": AmazonJsonStrategy,
    "JSON_SHOPEE": ShopeeJsonStrategy,
    "JSON_MAGALU": MagaluJsonStrategy,
    "HTML_ML": MercadoLivreHtmlStaticStrategy,
    "HTML_AMAZON": AmazonHtmlStaticStrategy,
    "HTML_SHOPEE": ShopeeHtmlStaticStrategy,
    "HTML_MAGALU": MagaluHtmlStaticStrategy,
}

#Mapeamento entre domínio e a ordem preferencial de estratégias
#As chaves correspondem aos domínios oficiais de cada marketplace
#Estratégias não registradas em ``STRATEGY_REGISTRY`` são ignoradas
DOMAIN_POLICIES: Dict[str, List[str]] = {
    "mercadolivre.com.br": ["JSON_ML", "HTML_ML", "PLAYWRIGHT"],
    "amazon.com.br": ["JSON_AMAZON", "HTML_AMAZON","PLAYWRIGHT"],
    "shopee.com.br": ["JSON_SHOPEE", "HTML_SHOPEE", "PLAYWRIGHT"],
    "magazineluiza.com.br": ["JSON_MAGALU", "HTML_MAGALU", "PLAYWRIGHT"],
}


def strategies_for(url: str) -> List[ScrapingStrategy]:
    """ Retorna instâncias de estratégias ordenadas para o domínio

    A resolução utiliza :func:`extract_hostname` para identificar o host da
    URL e então monta uma lista **sequencial** de instâncias conforme
    ``DOMAIN_POLICIES``. Estratégias desconhecidas são ignoradas e, caso o
    domínio não possua configuração específica, a estratégia padrão via
    Playwright é utilizada.
    """
    host = extract_hostname(url)

    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertence exatamente ao seu domínio """
        return host == domain or host.endswith("." + domain)

    for domain, names in DOMAIN_POLICIES.items():
        if _corresponds_domain(host, domain):
            return [
                STRATEGY_REGISTRY[name]()
                for name in names
                if name in STRATEGY_REGISTRY
            ]

    #Fallback para a estratégia padrão quando o domínio não é reconhecido
    return [PlaywrightDefaultStrategy()]
