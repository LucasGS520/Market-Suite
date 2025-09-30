from __future__ import annotations

""" Política de carregamento de etapas de pipeline por domínio

As configurações são carregadas de um arquivo YAML durante a inicialização
permitindo alterar a composição do pipeline sem nova publicação. Um 
`hot-reload` opcional recarrega o arquivo sempre que ele for modificado.
As políticas podem ser definidas por domínio e por contexto (como tipo de
página ou perfil do usuário), facilitando ajustes granulares sem alterar código.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Type, Literal, cast
import hashlib
import os

import structlog
import yaml

import market_scraper.services.pipeline_steps as pipeline_steps_module
from market_scraper.services.synergic_pipeline import PipelineStep
from market_scraper.utils.http_utils import extract_hostname
from market_scraper.utils_controllers.configuration.base_loader import calculate_file_hash
from shared.metrics.metrics_scraper import SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS
from shared.utils.logging_utils import sanitize_log_data


#Caminho do arquivo de configuração. Pode ser alterado via variável de ambiente ``DOMAIN_POLICY_FILE``
CONFIG_PATH = Path(os.getenv("DOMAIN_POLICY_FILE", Path(__file__).with_name("domain_policy.yaml")))

#Estruturas carregadas a partir do arquivo de configuração
@dataclass(frozen=True)
class StepDefinition:
    """ Representa a classe da etapa e argumentos padrão de construção """
    cls: Type[PipelineStep]
    default_options: Dict[str, Any]

PIPELINE_STEP_REGISTRY: Dict[str, StepDefinition] = {}
PIPELINE_POLICIES: Dict[str, Dict[str, List[str]]] = {}
PIPELINE_EXECUTION: Dict[str, Dict[str, str] | str] = {}
FEATURE_FLAGS: Dict[str, Dict[str, Dict[str, "FeatureFlagConfig"]]] = {}
PIPELINE_STEP_OPTIONS: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}

#Controle interno de hot-reload
_HOT_RELOAD = bool(os.getenv("DOMAIN_POLICY_HOT_RELOAD"))
_CONFIG_MTIME = 0.0
_CONFIG_HASH: str | None = None

#Indicador da última tentativa de carga do arquivo de políticas
CONFIG_LOAD_FAILED = False

logger = structlog.get_logger("domain_policy")

@dataclass(frozen=True)
class FeatureFlagConfig:
    """ Representa as opções configuradas para uma feature flag """
    enabled: bool
    rollout_percentage: float

@dataclass(frozen=True)
class FeatureFlagDecision:
    """ Resultado da avaliação de uma feature flag para um domínio/contexto """
    feature: str
    context: str
    enabled: bool
    config_enabled: bool
    rollout_percentage: float
    source: str | None
    identifier: str | None
    bucket_value: float | None
    configured: bool

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

def _normalize_step_options_structure(raw: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]:
    """ Normaliza configuração de argumentos padrão por contexto/etapa """
    normalized: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}
    for domain, entry in (raw or {}).items():
        if not isinstance(entry, dict):
            continue
        contexts: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for context_name, options in entry.items():
            if not isinstance(options, dict):
                continue
            step_options: Dict[str, Dict[str, Any]] = {}
            for step_name, values in options.items():
                if isinstance(values, dict):
                    step_options[step_name] = dict(values)
            if step_options:
                contexts[context_name] = step_options
        if contexts:
            normalized[domain] = contexts
    return normalized

def _select_options_for_context(entries: Dict[str, Dict[str, Any]] | None, context: str) -> Dict[str, Dict[str, Any]]:
    """ Combina opções padrão e específicas do contexto informado """
    if not entries:
        return {}
    
    combined: Dict[str, Dict[str, Any]] = {}
    default_opts = entries.get("default")
    if isinstance(default_opts, dict):
        combined = {key: dict(value) for key, value in default_opts.items() if isinstance(value, dict)}

    if context != "default":
        specific = entries.get(context)
        if isinstance(specific, dict):
            for step_name, options in specific.items():
                if not isinstance(options, dict):
                    continue
                merged = {**combined.get(step_name, {}), **options}
                combined[step_name] = merged

    return combined

def _merge_step_options(base: Dict[str, Dict[str, Any]], new_options: Dict[str, Dict[str, Any]]) -> None:
    """ Mescla opções de etapa preservando prioridades do domínio/contexto """
    for step_name, options in (new_options or {}).items():
        if not isinstance(options, dict):
            continue
        merged = {**base.get(step_name, {}), **options}
        base[step_name] = merged

def _normalize_flag_value(value: Any) -> FeatureFlagConfig | None:
    """ Converte valores diversos em ``FeatureFlagConfig`` """
    if isinstance(value, bool):
        return FeatureFlagConfig(enabled=value, rollout_percentage=100.0 if value else 0.0)
    if isinstance(value, (int, float)):
        rollout = max(0.0, min(float(value), 100.0))
        return FeatureFlagConfig(enabled=rollout > 0.0, rollout_percentage=rollout)
    if isinstance(value, dict):
        enabled_raw = value.get("enabled")
        rollout_raw = value.get("rollout_percentage", 100.0 if enabled_raw is not False else 0.0)
        try:
            rollout = float(rollout_raw)
        except (TypeError, ValueError):
            rollout = 100.0 if enabled_raw not in (False, None) else 0.0
        rollout = max(0.0, min(rollout, 100.0))
        enabled = bool(enabled_raw) if enabled_raw is not None else rollout > 0.0
        if not enabled:
            rollout = 0.0
        return FeatureFlagConfig(enabled=enabled, rollout_percentage=rollout)
    return None

def _normalize_flag_structure(raw: Dict[str, Any]) -> Dict[str, Dict[str, FeatureFlagConfig]]:
    """ Normaliza a estrutura de feature flags por domínio/contexto """
    normalized: Dict[str, Dict[str, FeatureFlagConfig]] = {}
    for domain, entry in (raw or {}).items():
        contexts: Dict[str, FeatureFlagConfig] = {}
        if isinstance(entry, dict):
            for context_name, value in entry.items():
                config = _normalize_flag_value(value)
                if config:
                    contexts[context_name] = config
        else:
            config = _normalize_flag_value(entry)
            if config:
                contexts["default"] = config
        if contexts:
            normalized[domain] = contexts
    return normalized

def load_config() -> None:
    """ Carrega as etapas do pipeline e políticas do arquivo configurado """
    global PIPELINE_STEP_REGISTRY, PIPELINE_POLICIES
    global PIPELINE_EXECUTION, FEATURE_FLAGS, _CONFIG_MTIME, _CONFIG_HASH
    global PIPELINE_STEP_OPTIONS, CONFIG_LOAD_FAILED

    if not CONFIG_PATH.exists():
        PIPELINE_STEP_REGISTRY = {}
        PIPELINE_POLICIES = {}
        PIPELINE_EXECUTION = {}
        FEATURE_FLAGS = {}
        PIPELINE_STEP_OPTIONS = {}
        _CONFIG_MTIME = 0.0
        _CONFIG_HASH = None
        CONFIG_LOAD_FAILED = False
        SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS.set(1)
        return

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as handler:
            data = yaml.safe_load(handler) or {}
    except yaml.YAMLError as exc:
        logger.error(
            "domain_policy_config_invalid",
            config_path=str(CONFIG_PATH),
            error=sanitize_log_data(str(exc)),
        )
        CONFIG_LOAD_FAILED = True
        SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS.set(0)
        return
    except OSError as exc:
        logger.exception(
            "domain_policy_config_read_error",
            config_path=str(CONFIG_PATH),
            error=sanitize_log_data(str(exc)),
        )
        CONFIG_LOAD_FAILED = True
        SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS.set(0)
        return
    
    #Mapeia etapas do pipeline sinérgico com opções padrão
    step_registry: Dict[str, StepDefinition] = {}
    for name, entry in (data.get("pipeline_steps") or {}).items():
        class_name: str | None = None
        default_options: Dict[str, Any] = {}
        if isinstance(entry, str):
            class_name = entry
        elif isinstance(entry, dict):
            class_name = entry.get("class")
            raw_options = entry.get("default_options") or entry.get("options") or {}
            if isinstance(raw_options, dict):
                default_options = {key: value for key, value in raw_options.items()}
        if not class_name:
            continue
        step_cls = getattr(pipeline_steps_module, class_name, None)
        if step_cls:
            step_registry[name] = StepDefinition(cls=step_cls, default_options=default_options)

    PIPELINE_STEP_REGISTRY = step_registry
    PIPELINE_POLICIES = _normalize_policy_structure(data.get("pipeline_policies") or {})
    PIPELINE_EXECUTION = data.get("pipeline_execution") or {}
    PIPELINE_STEP_OPTIONS = _normalize_step_options_structure(data.get("pipeline_step_options") or {})
    
    raw_flags = data.get("feature_flags") or {}
    flags: Dict[str, Dict[str, Dict[str, FeatureFlagConfig]]] = {}
    for feature, definitions in raw_flags.items():
        if not isinstance(definitions, dict):
            continue
        normalized = _normalize_flag_structure(definitions)
        if normalized:
            flags[feature] = normalized

    FEATURE_FLAGS = flags
    _CONFIG_MTIME = CONFIG_PATH.stat().st_mtime
    _CONFIG_HASH = calculate_file_hash(CONFIG_PATH)
    CONFIG_LOAD_FAILED = False
    SCRAPER_DOMAIN_POLICY_LAST_LOAD_SUCCESS.set(1)

def _compute_rollout_bucket(identifier: str) -> float:
    """ Calcula um valor de 0 a 100 a partir de um identificador estável """
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)
    return (value % 10000) / 100.0

def _resolve_flag_for_context(entries: Dict[str, FeatureFlagConfig] | None, context: str) -> FeatureFlagConfig | None:
    """ Localiza a congiguração apropriada para o contexto informado  """
    if not entries:
        return None
    if context in entries:
        return entries[context]
    return entries.get("default")

def feature_flag_config_for(feature: str, url: str, *, context: str = "default") -> tuple[FeatureFlagConfig | None, str | None]:
    """ Retorna a configuração de feature flag aplicada ao domínio/contexto """
    _reload_if_needed()

    host = extract_hostname(url)
    flags = FEATURE_FLAGS.get(feature)
    if not flags:
        return None, None
    
    def _corresponds_domain(host: str, domain: str) -> bool:
        """ Verifica se o host pertence extamente ao domínio informado """
        return host == domain or host.endswith("." + domain)
    
    for domain, contexts in flags.items():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            config = _resolve_flag_for_context(contexts, context)
            if config:
                return config, domain
            
    default_contexts = flags.get("default")
    if default_contexts:
        config = _resolve_flag_for_context(default_contexts, context)
        if config:
            return config, "default"
        
    return None, None

def evaluate_feature_flag(feature: str, url: str, *, context: str = "default", identifier: str | None = None, default_enabled: bool = True) -> FeatureFlagDecision:
    """ Avalia uma feature flag considerando rollout e fallback padrão """
    config, source = feature_flag_config_for(feature, url, context=context)
    identifier_value = identifier
    rollout_percentage = 100.0 if default_enabled else 0.0
    bucket: float | None = None

    if config is None:
        return FeatureFlagDecision(
            feature=feature,
            context=context,
            enabled=default_enabled,
            config_enabled=default_enabled,
            rollout_percentage=rollout_percentage,
            source=source,
            identifier=identifier_value,
            bucket_value=bucket,
            configured=False,
        )
    
    rollout_percentage = config.rollout_percentage
    config_enabled = config.enabled
    enabled = config_enabled

    if config_enabled and rollout_percentage < 100.0:
        base_identifier = identifier_value or url
        bucket = _compute_rollout_bucket(base_identifier)
        enabled = bucket < rollout_percentage
    elif not config_enabled:
        rollout_percentage = 0.0

    return FeatureFlagDecision(
        feature=feature,
        context=context,
        enabled=enabled,
        config_enabled=config_enabled,
        rollout_percentage=rollout_percentage,
        source=source,
        identifier=identifier_value,
        bucket_value=bucket,
        configured=True,
    )

def is_feature_enabled(feature: str, url: str, *, context: str = "default", identifier: str | None = None, default_enabled: bool = True) -> bool:
    """ Retorna apenas o resultado booleano de ``evaluate_feature_flag`` """
    decision = evaluate_feature_flag(
        feature,
        url,
        context=context,
        identifier=identifier,
        default_enabled=default_enabled,
    )
    return decision.enabled

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

    global _CONFIG_MTIME, _CONFIG_HASH
    current_mtime = CONFIG_PATH.stat().st_mtime
    current_hash = calculate_file_hash(CONFIG_PATH)
    if current_mtime != _CONFIG_MTIME or current_hash != _CONFIG_HASH:
        load_config()

def _select_names_for_context(names: Dict[str, List[str]] | List[str], context: str) -> List[str]:
    """ Retorna a lista de nomes respeitando o contexto informado """
    if isinstance(names, list):
        return list(names) if context == "default" else []
    return list(names.get(context) or names.get("default") or [])

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

    step_options: Dict[str, Dict[str, Any]] = {}

    default_step_options = PIPELINE_STEP_OPTIONS.get("default")
    _merge_step_options(step_options, _select_options_for_context(default_step_options, context))

    for domain, contexts in PIPELINE_STEP_OPTIONS.items():
        if domain == "default":
            continue
        if _corresponds_domain(host, domain):
            _merge_step_options(step_options, _select_options_for_context(contexts, context))
            break

    isinstance: List[PipelineStep] = []
    for name in selected_steps:
        definition = PIPELINE_STEP_REGISTRY.get(name)
        if not definition:
            continue
        kwargs = dict(definition.default_options)
        options = step_options.get(name)
        if options:
            kwargs.update(options)
        try:
            isinstance.append(definition.cls(**kwargs))
        except TypeError:
            try:
                isinstance.append(definition.cls())
            except TypeError:
                continue
    return isinstance

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
 
#Carrega a configuração na importação do módulo
load_config()
