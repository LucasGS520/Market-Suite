from __future__ import annotations

""" Política de seleção de estratégias por domínio

As estratégias e políticas são carregadas de um arquivo ``YAML`` em tempo
de inicialização, permitindo alterar o mapeamento sem nova publicação. Um
``hot-reload`` opcional pode ser ativado para recarregar o arquivo sempre
que ele for modificado. As políticas podem ser definidas por domínio e por
contexto (como tipo de página ou perfil de usuário), facilitando ajustes
granulares sem alteração de código.
"""

from pathlib import Path
from typing import Any, Dict, List, Type, Literal, cast
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
DOMAIN_POLICIES: Dict[str, Dict[str, List[str]]] = {}
PIPELINE_STEP_REGISTRY: Dict[str, Type[PipelineStep]] = {}
PIPELINE_POLICIES: Dict[str, Dict[str, List[str]]] = {}
STRATEGY_EXECUTION: Dict[str, Dict[str, str] | str] = {}
PIPELINE_EXECUTION: Dict[str, Dict[str, str] | str] = {}
RATE_LIMIT_POLICIES: Dict[str, Dict[str, int]] = {}


#Controle interno de hot-reload
_HOT_RELOAD = bool(os.getenv("DOMAIN_POLICY_HOT_RELOAD"))
_CONFIG_MTIME = 0.0

def _normalize_policy_structure(raw: Dict[str, Any]) -> Dict[str, Dict[str, List[str]]]:
    """ Normaliza estruturas de políticas aceitando listas simples ou blocos por contexto """
    normalized: Dict[str, Dict[str, List[str]]] = {}
    for domain, entry in (raw or {}).items():
        contexts: Dict[str, List[str]] = {}
        if isinstance(entry, dict):
            for context_name, names in entry.items():
                if isinstance(names, list):
                    contexts[context_name] = list(names)
        elif isinstance(entry, list):
            contexts["default"] = list(entry)
        if contexts:
            normalized[domain] = contexts
    return normalized

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
    DOMAIN_POLICIES = _normalize_policy_structure(data.get("policies") or {})
    
    #Mapeia etapas do pipeline sinérgico
    step_registry: Dict[str, Type[PipelineStep]] = {}
    for name, class_name in (data.get("pipeline_steps") or {}).items():
        step_cls = getattr(pipeline_steps_module, class_name, None)
        if step_cls:
            step_registry[name] = step_cls

    PIPELINE_STEP_REGISTRY = step_registry
    PIPELINE_POLICIES = _normalize_policy_structure(data.get("pipeline_policies") or {})
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

def _select_names_for_context(names: Dict[str, List[str]] | List[str], context: str) -> List[str]:
    """ Retorna a lista de nomes respeitando o contexto informado """
    if isinstance(names, list):
        return list(names) if context == "default" else []
    return list(names.get(context) or names.get("default") or [])

def strategies_for(url: str, *, context: str = "default") -> List[ScrapingStrategy]:
    """ Retorna instâncias de estratégias ordenadas para o domínio/contexto """
    _reload_if_needed()

    host = extract_hostname(url)

    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertence exatamente ao domínio informado """
        return host == domain or host.endswith("." + domain)

    selected_names: List[str] = []
    for domain, names in DOMAIN_POLICIES.items():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            selected_names = _select_names_for_context(names, context)
            break

    if not selected_names and "default" in DOMAIN_POLICIES:
        selected_names = _select_names_for_context(DOMAIN_POLICIES["default"], context)

    return [
        STRATEGY_REGISTRY[name]()
        for name in selected_names
        if name in STRATEGY_REGISTRY
    ]

def strategy_execution_mode_for(url: str, *, context: str = "default") -> Literal["sequential", "parallel", "conditional"]:
    """ Obtém o modo de execução das estratégias configurado para o domínio/contexto """
    _reload_if_needed()

    host = extract_hostname(url)
    default_contexts = STRATEGY_EXECUTION.get("default")

    def _resolve_context_modes(raw: Dict[str, str] | str | None) -> Dict[str, str]:
        """ Normaliza estruturas aceitando tanto ``str`` quanto ``dict`` """
        if isinstance(raw, str):
            return {"default": raw}
        return raw or {}
    
    default_modes = {
        key: _normalize_execution_mode(value)
        for key, value in _resolve_context_modes(default_contexts).items()
    }

    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertence exatamente ao domínio informado """
        return host == domain or host.endswith("." + domain)
    
    for domain, raw_modes in STRATEGY_EXECUTION.items():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            normalized = {
                key: _normalize_execution_mode(value)
                for key, value in _resolve_context_modes(raw_modes).items()
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
    
    selected_steps: List[str] = []
    for domain, contexts in PIPELINE_POLICIES.items():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            selected_steps = _select_names_for_context(contexts, context)
            break

    if not selected_steps and "default" in PIPELINE_POLICIES:
        selected_steps = _select_names_for_context(PIPELINE_POLICIES["default"], context)

    return [
        PIPELINE_STEP_REGISTRY[name]()
        for name in selected_steps
        if name in PIPELINE_STEP_REGISTRY
    ]

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
        """ Verifica se o host pertence exatamente ao domínio informado """
        return host == domain or host.endswith("." + domain)
    
    for domain, policy in RATE_LIMIT_POLICIES.items():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            return policy
        
    return default_policy
 
#Carrega a configuração na importação do módulo
load_config()
