""" Funções e utilidades compartilhadas entre os scrapers

Responsável apenas por obter e interpretar o HTML dos produtos.
Qualquer persistência de dados ou autenticação deve ser tratada
por camadas externas, como o módulo ``market_alert``. Também
realiza o pré-processamento dos dados, tratamento de status
especiais (bloqueios e ``NOT_MODIFIED``) e integração com cache.
"""

from __future__ import annotations

from typing import Literal, Any
from uuid import UUID

import asyncio
from urllib.parse import urlparse

from fastapi import HTTPException, status
import structlog

from market_scraper.utils.http_utils import extract_hostname
from market_scraper.utils.intelligent_cache import IntelligentCacheManager
from market_scraper.utils.http_cache import get_cache_headers
from market_scraper.utils.block_recovery import BlockRecoveryManager
from market_scraper.utils.robots_txt import RobotsTxtParser
from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.utils.mechanicalsoup_login import login_and_get_cookies
from market_scraper.utils.circuit_breaker import CircuitBreaker
from market_scraper.utils.pace_control import pace_controller_registry
from market_scraper.utils.session_identity import session_identity_manager

from shared.enums import BlockResult
from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from shared.metrics.metrics_scraper import SCRAPER_HTTP_BLOCKED_TOTAL, SCRAPER_URL_STATUS_TOTAL, SCRAPER_FEATURE_FLAG_TOTAL
from shared.utils.logging_utils import sanitize_log_data

from market_scraper.services.synergic_pipeline import SynergicPipeline
from market_scraper.services.domain_policy import (
    pipeline_steps_for,
    pipeline_execution_mode_for,
    evaluate_feature_flag,
)


#Logger estruturado para registrar o fluxo do scraping
logger = structlog.get_logger("scraper_common")

#Gerenciador de cache inteligente para produtos
cache_manager = IntelligentCacheManager()

#Gerencia identidade (User-Agent + cookies) entre requisições
identity_manager = session_identity_manager

#Validador simples de campos essenciais do scraping
validator = DataQualityValidator()

#Registro centralizado de controle de ritmo por domínio
pace_registry = pace_controller_registry

async def scrape_product_common_async(
    *,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping | CompetitorProductCreateScraping,
    product_type: Literal["monitored", "competitor"],
    pace_controller = None,
    circuit_breaker: CircuitBreaker | None = None,
    recovery_manager: BlockRecoveryManager | None = None,
    mechanicalsoup_config: dict | None = None,
    **extra_kwargs,
) -> dict:
    """ Orquestra o fluxo de scraping com cache e pipeline sinérgico

    A rotina verifica o cache inteligente e executa o ``SynergicPipeline``
    definido para o domínio/contexto. Cada etapa registra logs estruturados,
    persiste metadados seguros e renova o TTL do cache quando um resultado
    existente é reutilizado. O compartilhamento de contexto garante que etapas
    subsequentes aproveitem cookies, HTML renderizado ou outras dependências
    resolvidas previamente.
    """
    #Registra o início do fluxo de scraping
    normalized_url = url
    safe_log_url = sanitize_log_data(normalized_url)
    logger.info(
        "start_scraping", 
        url=safe_log_url, 
        product_type=product_type
    )

    cookies = None
    if mechanicalsoup_config:
        login_url = mechanicalsoup_config.get("url")
        logger.info(
            "mechanicalsoup_login", 
            url=sanitize_log_data(login_url)
        )
        try:
            cookies = await login_and_get_cookies(mechanicalsoup_config)
        except Exception as err:
            logger.warning(
                "mechanicalsoup_login_failed", 
                erro=sanitize_log_data(str(err))
            )
        else:
            extra_kwargs.setdefault("cookies", cookies)

    marketplace = extract_hostname(normalized_url)
    host_label = marketplace or "unknown"

    def _record_status(status_label: str) -> None:
        """ Atualiza contadores de métricas agregadas por domínio """
        SCRAPER_URL_STATUS_TOTAL.labels(url_host=host_label, status=status_label).inc()

    pace_ctrl = pace_controller or pace_registry.get(host_label)
    domain_circuit_breaker = circuit_breaker or pace_ctrl.circuit_breaker
    session_key = f"{user_id}:{product_type}"
    reference_text = getattr(payload, "name_identification", None) or normalized_url
    await pace_ctrl.wait_for_turn(
        circuit_key=host_label,
        identifier=session_key,
        humanized_text=reference_text,
        reflection_text=1.0,
    )

    parser = RobotsTxtParser(base_url=normalized_url)
    user_agent = identity_manager.get_user_agent(session_key, host=host_label)
    path = urlparse(normalized_url).path or "/"
    if not await parser.is_allowed(path, user_agent):
        SCRAPER_HTTP_BLOCKED_TOTAL.inc()
        _record_status("robots_blocked")
        logger.warning(
            "blocking_robots",
            url=safe_log_url,
            user_agent=user_agent
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso bloqueado pelo robots.txt do site",
        )

    #Respeita o crawl-delay recomendado pelo site
    delay = await parser.get_crawl_delay(user_agent)
    if delay:
        logger.info(
            "waiting_crawl_delay", 
            delay=delay
        )
        await asyncio.sleep(delay)

    logger.info(
        "checking_cache", 
        url=normalized_url
    )
    cached = cache_manager.get(marketplace=marketplace, url=normalized_url)
    if cached:
        logger.info(
            "cache_found", 
            url=safe_log_url
        )
        #Quando o valor armazenado possui campos auxiliares, retorna apenas os dados
        details = cached.get("data", cached)
        try:
            validator.validate(details)
        except ValueError as err:
            logger.info(
                "cache_invalid", 
                url=safe_log_url, 
                reason=sanitize_log_data(str(err))
            )
        else:
            cache_manager.touch(marketplace=marketplace, url=normalized_url)
            logger.info(
                "cache_used", 
                url=safe_log_url
            )
            _record_status("success")
            return {"status": "success", "details": details}
    else:
        logger.info(
            "cache_not_found", 
            url=safe_log_url
        )

    shared_context: dict[str, Any] = {
        "url": normalized_url,
        "product_type": product_type,
        "pace_controller": pace_ctrl,
        "identity": {"session_key": session_key, "host": host_label},
        "circuit_breaker": domain_circuit_breaker,
    }
    if cookies:
        identity_manager.reset_cookies(session_key, host=host_label)
        session_jar = identity_manager.get_cookies(session_key, host=host_label)
        session_jar.update(cookies)
        shared_context["cookies"] = session_jar
    else:
        shared_context["cookies"] = identity_manager.get_cookies(session_key, host=host_label)

    def _persist_success(details: dict[str, Any], *, extraction_method: str | None = None) -> None:
        """ Armazena dados válidos no cache inteligente com metadados """

        headers_cache = get_cache_headers(normalized_url)
        cache_value: dict[str, Any] = {"data": details}
        if headers_cache.get("etag") or headers_cache.get("last_modified"):
            cache_value["headers"] = headers_cache

        metadata: dict[str, Any] = {}
        if extraction_method:
            metadata["extraction_method"] = extraction_method

        safe_context_keys = {"content_signature", "selectorlib_template"}
        safe_context = {
            key: shared_context[key]
            for key in safe_context_keys
            if key in shared_context
        }
        if safe_context:
            metadata["context"] = safe_context

        if metadata:
            cache_value["metadata"] = metadata

        cache_manager.set(
            marketplace=marketplace,
            url=normalized_url,
            value=cache_value,
        )
        logger.info(
            "stored_cache", 
            url=normalized_url, 
            metadata_keys=list(metadata.keys())
        )

    #Determina o contexto a partir do tipo de produto, permitindo políticas granulares
    pipeline_context = "competitor" if product_type == "competitor" else "default"

    try:
        steps = pipeline_steps_for(normalized_url, context=pipeline_context)
    except TypeError:
        steps = pipeline_steps_for(normalized_url)
    pipeline_decision = evaluate_feature_flag(
        "synergic_pipeline",
        normalized_url,
        context=pipeline_context,
        identifier=f"{user_id}:{normalized_url}",
    )

    if not steps:
        SCRAPER_FEATURE_FLAG_TOTAL.labels("synergic_pipeline", "no_steps").inc()
        logger.error(
            "pipeline_unavailable",
            url=safe_log_url,
            context=pipeline_context,
        )
        _record_status("error")
        return {"status": "error", "detail": "Pipeline não configurado para o domínio"}

    if not pipeline_decision.enabled:
        SCRAPER_FEATURE_FLAG_TOTAL.labels("synergic_pipeline", "disabled").inc()
        logger.info(
            "pipeline_feature_disabled",
            url=safe_log_url,
            context=pipeline_context,
            rollout=pipeline_decision.rollout_percentage,
            feature_source=pipeline_decision.source,
            bucket_value=pipeline_decision.bucket_value,
        )
        _record_status("error")
        return {"status": "error", "detail": "Pipeline sinérgico desabilitado para o domínio"}

    SCRAPER_FEATURE_FLAG_TOTAL.labels("synergic_pipeline", "enabled").inc()
    execution_mode = pipeline_execution_mode_for(normalized_url, context=pipeline_context)
    logger.info(
        "running_pipeline",
        url=safe_log_url,
        context=pipeline_context,
        execution_mode=execution_mode,
        steps=len(steps),
        rollout=pipeline_decision.rollout_percentage,
        feature_source=pipeline_decision.source,
        bucket_value=pipeline_decision.bucket_value,
    )
    pipeline = SynergicPipeline(steps=steps, execution_mode=execution_mode)
    pipeline_result = await pipeline.run(shared_context)
    shared_context.update(pipeline_result.get("shared_context", {}))

    def _message_fail(result: dict[str, Any]) -> str:
        """ Define mensagem amigável quando o pipeline não produz dados válidos """
        for entry in result.get("results", []):
            if entry.get("detail"):
                return str(entry["detail"])
            if entry.get("validation_error"):
                return f"Dados inválidos na etapa: {entry['validation_error']}"
        return "Nenhuma etapa do pipeline obteve dados válidos"
    
    for entry in pipeline_result.get("results", []):
        status_step = entry.get("status")
        if status_step == "success" and entry.get("details"):
            pipeline_details = entry["details"]
            try:
                validator.validate(pipeline_details)
            except ValueError as err:
                logger.info(
                    "pipeline_invalid_data",
                    erro=sanitize_log_data(str(err)),
                )
                continue
            method = entry.get("extraction_method")
            _persist_success(pipeline_details, extraction_method=method)
            logger.info(
                "pipeline_short_circuit",
                url=safe_log_url,
                step=method,
            )
            _record_status("success")
            return {"status": "success", "details": pipeline_details}
        
        if status_step == "NOT_MODIFIED":
            cached_pipeline = cache_manager.get(marketplace=marketplace, url=normalized_url)
            if cached_pipeline:
                cache_manager.touch(marketplace=marketplace, url=normalized_url)
                logger.info(
                    "pipeline_not_modified",
                    url=safe_log_url,
                )
                _record_status("not_modified")
                return {"status": "NOT_MODIFIED", "details": cached_pipeline}
    
    pipeline_status = pipeline_result.get("status") or "error"
    pipeline_details = pipeline_result.get("details")

    if pipeline_status == "success" and isinstance(pipeline_details, dict):
        try:
            #Garante que os campos essenciais estejam corretos
            validator.validate(pipeline_details)
        except ValueError as err:
            #Retorna informação de dado inválido
            logger.info(
                "pipeline_invalid_data",
                erro=sanitize_log_data(str(err)),
            )
        else:
            _persist_success(
                pipeline_details,
                extraction_method=pipeline_result.get("extraction_method"),
            )
            logger.info(
                "pipeline_success_fallback",
                url=safe_log_url,
            )
            _record_status("success")
            return {"status": "success", "details": pipeline_details}
        
    if pipeline_status == "NOT_MODIFIED":
        cached_pipeline = cache_manager.get(marketplace=marketplace, url=normalized_url)
        if cached_pipeline:
            cache_manager.touch(marketplace=marketplace, url=normalized_url)
            logger.info(
                "pipeline_not_modified",
                url=safe_log_url,
            )
            _record_status("not_modified")
            return {"status": "NOT_MODIFIED", "details": cached_pipeline}
        _record_status("not_modified")
        return {"status": "NOT_MODIFIED"}
    
    special_status = {b.value for b in BlockResult}
    if pipeline_status in special_status:
        SCRAPER_HTTP_BLOCKED_TOTAL.inc()
        _record_status(pipeline_status or "blocked")
        logger.warning(
            "special_status",
            status=pipeline_status,
            url=safe_log_url,
        )
        return {"status": pipeline_status}

    message = _message_fail(pipeline_result)
    logger.error(
        "pipeline_failed",
        url=safe_log_url,
        details=sanitize_log_data(message),
        status=pipeline_status,
    )
    _record_status("error")
    return {"status": "error", "detail": message}

def scrape_product_common(
    url: str,
    user_id: UUID,
    payload,
    product_type: Literal["monitored", "competitor"],
    pace_controller = None,
    circuit_breaker: CircuitBreaker | None = None,
    recovery_manager: BlockRecoveryManager | None = None,
    mechanicalsoup_config: dict | None = None,
    **extra_kwargs,
) -> dict:
    """ Executa ``scrape_product_common_async`` de maneira síncrono """
    logger.info(
        "start_scraping_sync", 
        url=sanitize_log_data(url), 
        product_type=product_type
    )
    return asyncio.run(
        scrape_product_common_async(
            url=url,
            user_id=user_id,
            payload=payload,
            product_type=product_type,
            pace_controller=pace_controller,
            circuit_breaker=circuit_breaker,
            recovery_manager=recovery_manager,
            mechanicalsoup_config=mechanicalsoup_config,
            **extra_kwargs,
        )
    )
