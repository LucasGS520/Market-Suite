""" Orquestra utilitários obrigatórios antes da execução do pipeline """

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import UUID
from urllib.parse import urlparse

import asyncio
import structlog
from fastapi import HTTPException, status

from shared.metrics.metrics_scraper import SCRAPER_HTTP_BLOCKED_TOTAL
from shared.utils.logging_utils import sanitize_log_data

from market_scraper.utils.http_utils import extract_hostname
from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.utils.cache_adapter import CacheAdapter
from market_scraper.utils.robots_txt import RobotsTxtParser
from market_scraper.utils_controllers.pace_control import DomainPaceController, PaceControllerRegistry, pace_controller_registry
from market_scraper.utils_controllers.session_identity import SessionIdentityManager


logger = structlog.get_logger("pre_pipeline")

@dataclass
class PrePipelineResult:
    """ Representa o estado produzido antes de inicar o pipeline sinérgico """
    shared_context: dict[str, Any]
    pace_controller: DomainPaceController
    marketplace: Optional[str]
    cached_response: Optional[dict[str, Any]]

class PrePipelineOrchestrator:
    """ Executa robots.txt, controle de ritmo e cache antes do pipeline """
    def __init__(
        self,
        *,
        cache_adapter: CacheAdapter,
        identity_manager: SessionIdentityManager,
        validator: DataQualityValidator,
        pace_registry: PaceControllerRegistry | None = None,
        robots_parser_factory: Callable[[str], RobotsTxtParser] | None = None,
        blocked_counter_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.cache_adapter = cache_adapter
        self.identity_manager = identity_manager
        self.validator = validator
        self.pace_registry = pace_registry or pace_controller_registry
        self.robots_parser_factory = robots_parser_factory or RobotsTxtParser
        self.blocked_counter_factory = blocked_counter_factory or (lambda: SCRAPER_HTTP_BLOCKED_TOTAL)
    
    async def run(
        self,
        *,
        url: str,
        user_id: UUID,
        product_type: str,
        reference_text: str,
        circuit_breaker: Optional[Any] = None,
        pace_controller: DomainPaceController | None = None,
        seed_cookies: Optional[Any] = None,
    ) -> PrePipelineResult:
        """ Executa verificações de ritmo, robots.txt e cache antes do pipeline 
        
        O método retorna um ``PrePipelineResult`` contendo o ``shared_context``
        que deverá ser consumido pelas etapas do pipeline, o controlador de ritmo
        em uso e (quando aplicável) uma resposta derivada do cache que permite
        encerrar a execução antecipadamente.
        """
        marketplace = extract_hostname(url)
        host_label = marketplace or "unknown"
        safe_log_url = sanitize_log_data(url)

        controller = pace_controller or self.pace_registry.get(host_label)
        await controller.wait_for_turn(
            circuit_key=host_label,
            identifier=f"{user_id}:{product_type}",
            humanized_text=reference_text,
            reflection_time=1.0,
        )

        session_key = f"{user_id}:{product_type}"
        user_agent = self.identity_manager.get_user_agent(session_key, host=host_label)

        parser = self.robots_parser_factory(base_url=url)
        path = urlparse(url).path or "/"
        if not await parser.is_allowed(path, user_agent):
            self.blocked_counter_factory().inc()
            logger.warning(
                "blocking_robots",
                url=safe_log_url,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso bloqueado pelo robots.txt do site",
            )
        
        delay = await parser.get_crawl_delay(user_agent)
        if delay:
            logger.info("waiting_crawl_delay", delay=delay, url=safe_log_url)
            await asyncio.sleep(delay)

        logger.info("checking_cache", url=safe_log_url)
        #O adaptador abstrai versões diferentes das chaves de cache sem alterar chamadores
        cached_entry = self.cache_adapter.get(marketplace=marketplace, url=url)
        cached_response: Optional[dict[str, Any]] = None

        if cached_entry:
            logger.info("cache_found", url=safe_log_url)
            details = cached_entry.get("data", cached_entry)
            try:
                self.validator.validate(details)
            except ValueError as err:
                logger.info(
                    "cache_invalid",
                    url=safe_log_url,
                    reason=sanitize_log_data(str(err)),
                )
            else:
                self.cache_adapter.touch(marketplace=marketplace, url=url)
                cached_response = {"status": "success", "details": details}
                logger.info("cache_used", url=safe_log_url)
        else:
            logger.info("cache_not_found", url=safe_log_url)

        identity_data = {"session_key": session_key, "host": host_label, "user_agent": user_agent}
        cookies_jar = self.identity_manager.get_cookies(session_key, host=host_label)
        if seed_cookies:
            self.identity_manager.reset_cookies(session_key, host=host_label)
            cookies_jar = self.identity_manager.get_cookies(session_key, host=host_label)
            cookies_jar.update(seed_cookies)

        shared_context: dict[str, Any] = {
            "url": url,
            "product_type": product_type,
            "pace_controller": controller,
            "identity": identity_data,
            "circuit_breaker": circuit_breaker or controller.circuit_breaker,
            "cookies": cookies_jar,
        }

        return PrePipelineResult(
            shared_context=shared_context,
            pace_controller=controller,
            marketplace=marketplace,
            cached_response=cached_response,
        )
 