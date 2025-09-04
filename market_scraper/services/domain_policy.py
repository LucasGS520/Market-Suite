from __future__ import annotations

""" Política de seleção de estratégias por domínio

As estratégias e políticas são carregadas de um arquivo ``YAML`` em tempo
de inicialização, permitindo alterar o mapeamento sem nova publicação. Um
``hot-reload`` opcional pode ser ativado para recarregar o arquivo sempre
que ele for modificado. 
"""

from pathlib import Path
from typing import Dict, List, Type
import os

import yaml

import market_scraper.strategies as strategies_module
from market_scraper.strategies import ScrapingStrategy
from market_scraper.utils.http_utils import extract_hostname


#Caminho do arquivo de configuração. Pode ser alterado via variável de ambiente ``DOMAIN_POLICY_FILE``
CONFIG_PATH = Path(os.getenv("DOMAIN_POLICY_FILE", Path(__file__).with_name("domain_policy.yaml")))

#Estruturas carregadas a partir do arquivo de configuração
STRATEGY_REGISTRY: Dict[str, Type[ScrapingStrategy]] = {}
DOMAIN_POLICIES: Dict[str, List[str]] = {}

#Controle interno de hot-reload
_HOT_RELOAD = bool(os.getenv("DOMAIN_POLICY_HOT_RELOAD"))
_CONFIG_MTIME = 0.0

def load_config() -> None:
    """ Carrega as estratégias e políticas do arquivo configurado """
    global STRATEGY_REGISTRY, DOMAIN_POLICIES, _CONFIG_MTIME

    if not CONFIG_PATH.exists():
        STRATEGY_REGISTRY = {}
        DOMAIN_POLICIES = {}
        _CONFIG_MTIME = 0.0
        return

    with CONFIG_PATH.open("r", encoding="utf-8") as handler:
        data = yaml.safe_load(handler) or {}

    #Mapeia nomes para classes reais baseadas nas strings fornecidas
    registry: Dict[str, Type[ScrapingStrategy]] = {}
    for name, class_name in (data.get("strategies") or {}).items():
        strategy_cls = getattr(strategies_module, class_name, None)
        if strategy_cls:
            registry[name] = strategy_cls

    STRATEGY_REGISTRY = registry
    DOMAIN_POLICIES = data.get("policies") or {}
    _CONFIG_MTIME = CONFIG_PATH.stat().st_mtime

def enable_hot_reload() -> None:
    """ Habilita o recarregamento automático do arquivo de configuração """
    global _HOT_RELOAD
    _HOT_RELOAD = True

def _reload_if_needed() -> None:
    """ Recarrega o arquivo se hot-reload estiver ativo e houver mudanças """
    if not _HOT_RELOAD or not CONFIG_PATH.exists():
        return

    global _CONFIG_MTIME
    current_mtime = CONFIG_PATH.stat().st_mtime
    if current_mtime != _CONFIG_MTIME:
        load_config()

def strategies_for(url: str) -> List[ScrapingStrategy]:
    """ Retorna instâncias de estratégias ordenadas para o domínio

    A resolução utiliza :func:`extract_hostname` para identificar o host da
    URL e então monta uma lista **sequencial** de instâncias conforme
    ``DOMAIN_POLICIES``. Estratégias desconhecidas são ignoradas e, caso o
    domínio não possua configuração específica, nenhuma estratégia pesada
    é aplicada nesse momento (Se necessário Playwright add em etapas futuras)
    """
    _reload_if_needed()

    host = extract_hostname(url)

    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertence exatamente ao domínio informado """
        return host == domain or host.endswith("." + domain)

    for domain, names in DOMAIN_POLICIES.items():
        if _corresponds_domain(host, domain):
            return [
                STRATEGY_REGISTRY[name]()
                for name in names
                if name in STRATEGY_REGISTRY
            ]

    #Quando domínio não é reconhecido, nenhuma estratégia é retornada
    return []

#Carrega a configuração na importação do módulo
load_config()
