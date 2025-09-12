from __future__ import annotations

""" Política de configuração de pipelines por domínio 

Este módulo permite definir, via arquivo ``YAML``, quais etapas do
pipeline devem ser utilizadas para um domínio específico ou para um 
tipo de página. A configuração é carregada em tempo de execução e 
pode ser atualizada dinamicamente.
"""

from pathlib import Path
from typing import Dict, List, Type
import os

import yaml

from market_scraper.services.synergic_pipeline import PipelineStep
from market_scraper.utils.http_utils import extract_hostname


CONFIG_PATH = Path(
    os.getenv("PIPELINE_POLICY_FILE", Path(__file__).with_name("pipeline_policy.yaml"))
)

STEP_REGISTRY: Dict[str, Type[PipelineStep]] = {}
PIPELINE_POLICIES: Dict[str, Dict[str, List[str]]] = {}

_HOT_RELOAD = bool(os.getenv("PIPELINE_POLICY_HOT_RELOAD"))
_CONFIG_MTIME = 0.0

def load_config() -> None:
    """ Carrega o arquivo de configuração de pipelines """
    global STEP_REGISTRY, PIPELINE_POLICIES, _CONFIG_MTIME

    if not CONFIG_PATH.exists():
        STEP_REGISTRY = {}
        PIPELINE_POLICIES = {}
        _CONFIG_MTIME = 0.0
        return
    
    with CONFIG_PATH.open("r", encoding="utf-8") as handler:
        data = yaml.safe_load(handler) or {}

    registry: Dict[str, Type[PipelineStep]] = {}
    for name, class_name in (data.get("steps") or {}).items():
        #As etapas devem estar disponíveis no escopo ``market_scraper.services``
        module = __import__("market_scraper.services", fromlist=[class_name])
        step_cls = getattr(module, class_name, None)
        if step_cls:
            registry[name] = step_cls

    STEP_REGISTRY = registry
    PIPELINE_POLICIES = data.get("pipelines") or {}
    _CONFIG_MTIME = CONFIG_PATH.stat().st_mtime

def _reload_if_needed() -> None:
    """ Recarrega o arquivo se o modo hot-reload estiver ativo """
    if not _HOT_RELOAD or not CONFIG_PATH.exists():
        return
    
    global _CONFIG_MTIME
    current_mtime = CONFIG_PATH.stat().st_mtime
    if current_mtime != _CONFIG_MTIME:
        load_config()

def steps_for(url: str, page_type: str = "default") -> List[PipelineStep]:
    """ Retorna instâncias das etapas configuradas para o domínio """
    _reload_if_needed()
    host = extract_hostname(url)

    def _matches(host: str, domain: str) -> bool:
        return host == domain or host.endswith("." + domain)
    
    for domain, config in PIPELINE_POLICIES.items():
        if _matches(host, domain):
            names = config.get(page_type) or config.get("default") or []
            return [STEP_REGISTRY[name]() for name in names if name in STEP_REGISTRY]
        
    return []

load_config()

__all__ = ["steps_for", "load_config"]
