from __future__ import annotations

""" Orquestrador de múltiplas estratégias de scraping

Esta classe centraliza a execução sequencial das estratégias de scraping
para uma determinada URL. A cada tentativa bem sucedida de coleta os dados
são validados e métricas de observabilidade são atualizadas.
"""

from typing import Callable, Literal, Awaitable, Any
from uuid import UUID

import asyncio
from fastapi import HTTPException, status
import structlog

from market_scraper.services.domain_policy import strategies_for
from market_scraper.strategies import ScrapingStrategy
from market_scraper.utils.data_quality_validator import DataQualityValidator
from market_scraper.utils.circuit_breaker import CircuitBreaker
from market_scraper.utils.rate_limiter import RateLimiter
from market_scraper.utils.block_recovery import BlockRecoveryManager
from market_scraper.utils.throttle_manager import ThrottleManager
from shared.metrics.metrics_scraper import SCRAPER_STRATEGY_TOTAL, SCRAPER_FALLBACK_TOTAL


#Logger configurado para este módulo
logger = structlog.get_logger("multi_strategy_orchestrator")

class MultiStrategyScraperOrchestrator:
    """ Controla a ordem e a validação das estratégias de scraping """

    def __init__(
        self,
        *,
        strategy_selector: Callable[[str], list[ScrapingStrategy]] | None = None,
        validator: DataQualityValidator | None = None,
        strategy_timeout: float | None = None,
        throttle_manager: ThrottleManager | None = None,
        dependency_resolvers: dict[str, Callable[..., Awaitable[dict | None]]] | None = None,
    ) -> None:
        """ Define dependências opcionais para o orquestrador

        ``strategy_selector`` permite injetar uma função customizada que
        retorna as estratégias disponíveis para uma URL. ``validator`` é
        utilizado para conferir a qualidade dos dados retornados.
        ``strategy_timeout`` define o tempo máximo para execução de cada
        estratégia. ``throttle_manager`` controla o ritmo das requisições
        HTML, evitando excesso de chamadas ao mesmo domínio. ``dependency_resolvers``
        contém funções assíncronas que resolvem dependências declaradas pelas
        estratégias antes da execução.
        """
        self._strategy_selector = strategy_selector or strategies_for
        self._validator = validator or DataQualityValidator()
        self._strategy_timeout = strategy_timeout
        self._throttle_manager = throttle_manager or ThrottleManager(rate=1.0, capacity=1)
        self._dependency_resolvers = dependency_resolvers or {}

    async def scrape(
        self,
        *,
        url: str,
        user_id: UUID,
        payload,
        product_type: Literal["monitored", "competitor"],
        strategies: list[ScrapingStrategy] | None = None,
        execution_mode: Literal["sequential", "parallel", "conditional"] = "sequential",
        shared_context: dict | None = None,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None,
        **kwargs,
    ) -> dict:
        """ Executa as estratégias de scraping conforme o modo definido

        ``strategies`` permite receber um pipeline personalizado de estratégias,
        tornando o orquestrador configurável em tempo de execução. ``execution_mode``
        define como o pipeline será processado: ``sequential`` (padrão), ``parallel``
        ou ``conditional``. ``shared_context`` é um dicionário mutável usado para 
        compartilhar dados intermediários entre estratégias (como cookies ou HTML
        pré-renderizado). Antes de cada etapa, as dependências declaradas são
        resolvidas via ``dependency_resolvers``. Os parâmetros extras em ``kwargs``
        são repassados para cada estratégia.
        """
        strategies = strategies or self._strategy_selector(url)
        if not strategies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL não suportada",
            )

        shared_context = shared_context or {}

        async def _resolve_dependency(name: str) -> None:
            """ Garante que a dependência esteja presente no contexto """
            if name in shared_context:
                return
            resolver = self._dependency_resolvers.get(name)
            if resolver is None:
                logger.warning("dependency_resolver_missing", dependency=name)
                return
            try:
                ctx_update = await resolver(
                    shared_context=shared_context,
                    url=url,
                    user_id=user_id,
                    payload=payload,
                    **kwargs,
                )
                if isinstance(ctx_update, dict):
                    shared_context.update(ctx_update)
            except Exception as err:
                logger.warning("dependency_resolver_error", dependency=name, erro=err)

        async def _run_strategy(strategy: ScrapingStrategy) -> tuple[ScrapingStrategy, dict, str]:
            """ Executa uma estratégia individual com tratamento de erros """
            try:
                result = await asyncio.wait_for(
                    strategy.get_data(
                        url=url,
                        headers=None,
                        user_id=user_id,
                        payload=payload,
                        product_type=product_type,
                        rate_limiter=rate_limiter,
                        circuit_breaker=circuit_breaker,
                        recovery_manager=recovery_manager,
                        throttle_manager=self._throttle_manager,
                        shared_context=shared_context,
                        **kwargs,
                    ),
                    timeout=self._strategy_timeout,
                )
                status_label = result.get("status", "error")
            except asyncio.TimeoutError:
                #Tempo excedido: marca como falha e registra aviso
                logger.warning("strategy_timeout", strategy=strategy.__class__.__name__)
                result = {"status": "error"}
                status_label = "timeout"
            except Exception as err:
                #Registra o erro para facilitar diagnóstico no scraping
                logger.exception("unexpected_error_strategy", erro=(err))
                #Qualquer exceção marca a execução como erro
                result = {"status": "error"}
                status_label = "exception"
            return strategy, result, status_label
        
        result: dict = {"status": "error"}

        #Execução paralela das estratégias
        if execution_mode == "parallel":
            deps: set[str] = set()
            for s in strategies:
                if s.supports_url(url):
                    deps.update(getattr(s, "dependencies", set()))
            for dep in deps:
                await _resolve_dependency(dep)

            tasks = []
            skipped = 0
            for s in strategies:
                if not s.supports_url(url):
                    continue
                dep_set = getattr(s, "dependencies", set())
                if any(d not in shared_context for d in dep_set):
                    skipped += 1
                    continue
                tasks.append(_run_strategy(s))

            responses = await asyncio.gather(*tasks)

            result_found = False
            fallback_counted = False

            for idx, (strategy, resp, status_label) in enumerate(responses):
                details = resp.get("details")
                if details is not None:
                    try:
                        self._validator.validate(details)
                    except ValueError:
                        status_label = "invalid"
                        resp = {"status": "error"}

                SCRAPER_STRATEGY_TOTAL.labels(
                    strategy.__class__.__name__, status_label
                ).inc()

                if not result_found and status_label in ("success", "NOT_MODIFIED"):
                    result = resp
                    result_found = True
                elif not fallback_counted:
                    SCRAPER_FALLBACK_TOTAL.inc()
                    fallback_counted = True

                ctx_update = resp.get("shared_context")
                if isinstance(ctx_update, dict):
                    shared_context.update(ctx_update)

            for _ in range(skipped):
                SCRAPER_FALLBACK_TOTAL.inc()

            return result
        
        #Execução sequencial ou condicional
        for idx, strategy in enumerate(strategies):
            if not strategy.supports_url(url):
                continue

            deps = getattr(strategy, "dependencies", set())
            for dep in deps:
                await _resolve_dependency(dep)
            if any(d not in shared_context for d in deps):
                if idx < len(strategies) - 1:
                    SCRAPER_FALLBACK_TOTAL.inc()
                continue
 
            if execution_mode == "conditional" and hasattr(strategy, "should_run"):
                if not strategy.should_run(shared_context):
                    continue

            strategy_obj, resp, status_label = await _run_strategy(strategy)
            details = resp.get("details")
            if details is not None:
                try:
                    #Valida dados essenciais mesmo quando o dicionário está vazio, antes de aceitar o resultado
                    self._validator.validate(details)
                except ValueError:
                    status_label = "invalid"
                    resp = {"status": "error"}

            #Registra a execução da estratégia com o status obtido
            SCRAPER_STRATEGY_TOTAL.labels(
                strategy_obj.__class__.__name__, status_label
            ).inc()

            ctx_update = resp.get("shared_context")
            if isinstance(ctx_update, dict):
                shared_context.update(ctx_update)

            if status_label in ("success", "NOT_MODIFIED"):
                result = resp
                result["extraction_method"] = strategy_obj.__class__.__name__
                break

            #Caso o resultado não seja aproveitável, registra fallback
            if idx < len(strategies) - 1:
                SCRAPER_FALLBACK_TOTAL.inc()

        return result

__all__ = ["MultiStrategyScraperOrchestrator"]
