from __future__ import annotations

""" Política de seleção de estratégias por domínio

As estratégias e políticas são carregadas de um arquivo ``YAML`` em tempo
de inicialização, permitindo alterar o mapeamento sem nova publicação. Um
``hot-reload`` opcional pode ser ativado para recarregar o arquivo sempre
que ele for modificado. 
"""

from pathlib import Path
from typing import Dict, List, Type, Literal, cast
import os

import yaml

import market_scraper.strategies as strategies_module
import market_scraper.services.pipeline_steps as pipeline_steps_module
from market_scraper.strategies import ScrapingStrategy
from market_scraper.services.synergic_pipeline import PipelineStep
from market_scraper.utils.http_utils import extract_hostname


#Caminho do arquivo de configuração. Pode ser alterado via variável de ambiente ``DOMAIN_POLICY_FILE``
CONFIG_PATH = Path(os.getenv("DOMAIN_POLICY_FILE", Path(__file__).with_name("domain_policy.yaml")))

#Estruturas carregadas a partir do arquivo de configuração
STRATEGY_REGISTRY: Dict[str, Type[ScrapingStrategy]] = {}
DOMAIN_POLICIES: Dict[str, List[str]] = {}
PIPELINE_STEP_REGISTRY: Dict[str, Type[PipelineStep]] = {}
PIPELINE_POLICIES: Dict[str, Dict[str, List[str]]] = {}
STRATEGY_EXECUTION: Dict[str, str] = {}
PIPELINE_EXECUTION: Dict[str, Dict[str, str] | str] = {}
RATE_LIMIT_POLICIES: Dict[str, Dict[str, int]] = {}


#Controle interno de hot-reload
_HOT_RELOAD = bool(os.getenv("DOMAIN_POLICY_HOT_RELOAD"))
_CONFIG_MTIME = 0.0

def load_config() -> None:
    """ Carrega as estratégias e políticas do arquivo configurado """
    global STRATEGY_REGISTRY, DOMAIN_POLICIES, PIPELINE_STEP_REGISTRY
    global PIPELINE_POLICIES, STRATEGY_EXECUTION, PIPELINE_EXECUTION, RATE_LIMIT_POLICIES, _CONFIG_MTIME

    if not CONFIG_PATH.exists():
        STRATEGY_REGISTRY = {}
        DOMAIN_POLICIES = {}
        PIPELINE_STEP_REGISTRY = {}
        PIPELINE_POLICIES = {}
        STRATEGY_EXECUTION = {}
        PIPELINE_EXECUTION = {}
        RATE_LIMIT_POLICIES = {}
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

    #Mapeia etapas do pipeline sinérgico
    step_registry: Dict[str, Type[PipelineStep]] = {}
    for name, class_name in (data.get("pipeline_steps") or {}).items():
        step_cls = getattr(pipeline_steps_module, class_name, None)
        if step_cls:
            step_registry[name] = step_cls

    PIPELINE_STEP_REGISTRY = step_registry
    PIPELINE_POLICIES = data.get("pipeline_policies") or {}
    STRATEGY_EXECUTION = data.get("strategy_execution") or {}
    PIPELINE_EXECUTION = data.get("pipeline_execution") or {}

    raw_limits = data.get("rate_limits") or {}
    limits: Dict[str, Dict[str, int]] = {}
    for domain, config in raw_limits.items():
        if not isinstance(config, dict):
            continue
        max_requests = config.get("max_requests")
        window = config.get("window")
        try:
            max_requests_int = int(max_requests)
            window_int = int(window)
        except (TypeError, ValueError):
            continue
        if max_requests_int <= 0 or window_int <= 0:
            continue
        limits[domain] = {"max_requests": max_requests_int, "window": window_int}

    RATE_LIMIT_POLICIES = limits
    _CONFIG_MTIME = CONFIG_PATH.stat().st_mtime

def _normalize_execution_mode(value: str | None) -> Literal["sequential", "parallel", "conditional"]:
    """ Normaliza o modo de execução aceitando apenas valores suportados """
    if not value:
        return "sequential"
    mode = value.lower()
    if mode in {"parallel", "conditional", "sequential"}:
        return cast(Literal["sequential", "parallel", "conditional"], mode)
    return "sequential"

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

def strategy_execution_mode_for(url: str) -> Literal["sequential", "parallel", "conditional"]:
    """ Obtém o modo de execução das estratégias configurado para o domínio """
    _reload_if_needed()

    host = extract_hostname(url)
    default_mode = _normalize_execution_mode(STRATEGY_EXECUTION.get("default"))

    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertence exatamente ao domínio informado """
        return host == domain or host.endswith("." + domain)
    
    for domain, mode in STRATEGY_EXECUTION.items():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            return _normalize_execution_mode(mode)
        
    return default_mode

def pipeline_steps_for(url: str, *, context: str = "default") -> List[PipelineStep]:
    """ Retorna intâncias de etapas de pipeline para o domínio
    
    ``context`` permite selecionar variações de pipeline definidas para o 
    domínio. Caso o contexto não exista, é utilizada a chave ``default``.
    Etapas desconhecidas são ignoradas e, se o domínio não estiver 
    configurado, é retornada uma lista vazia.
    """
    _reload_if_needed()

    host = extract_hostname(url)

    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertence exatamente ao domínio informado """
        return host == domain or host.endswith("." + domain)
    
    for domain, contexts in PIPELINE_POLICIES.items():
        if _corresponds_domain(host, domain):
            step_names = contexts.get(context) or contexts.get("default") or []
            return [
                PIPELINE_STEP_REGISTRY[name]()
                for name in step_names
                if name in PIPELINE_STEP_REGISTRY
            ]
        
    return []

def pipeline_execution_mode_for(url: str, *, context: str = "default") -> Literal["sequential", "parallel", "conditional"]:
    """ Retorna o modo de execução do pipeline para o domínio/contexto informado """
    _reload_if_needed()

    host = extract_hostname(url)
    default_contexts = PIPELINE_EXECUTION.get("default")

    def _resolve_context_modes(raw: Dict[str, str] | str | None) -> Dict[str, str]:
        """ Normaliza estruturas aceitando tanto ``str`` quanto ``dict`` """
        if isinstance(raw, str):
            return {"default": raw}
        return raw or {}
    
    default_modes = {
            k: _normalize_execution_mode(v)
            for k, v in _resolve_context_modes(default_contexts).items()
    }

    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertence exatamente ao domínio informado """
        return host == domain or host.endswith("." + domain)
    
    for domain, contexts in PIPELINE_EXECUTION.items():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            normalized = {
                key: _normalize_execution_mode(value)
                for key, value in _resolve_context_modes(contexts).items()
            }
            return (
                normalized.get(context)
                or normalized.get("default")
                or default_modes.get(context)
                or default_modes.get("default", "sequential")
            )
        
    return (
        default_modes.get(context)
        or default_modes.get("default", "sequential")
    )

def rate_limit_policy_for(url: str) -> Dict[str, int] | None:
    """ Retorna a política de rate limit configurada para o domínio """
    _reload_if_needed()

    host = extract_hostname(url)
    default_policy = RATE_LIMIT_POLICIES.get("default")

    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertemce exatamente ao domínio informado """
        return host == domain or host.endswith("." + domain)
    
    for domain, policy in RATE_LIMIT_POLICIES.iems():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            return policy
        
    return default_policy
 
#Carrega a configuração na importação do módulo
load_config()
