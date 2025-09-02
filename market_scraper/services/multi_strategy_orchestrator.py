from __future__ import annotations

""" Orquestrador de múltiplas estratégias de scraping

Esta classe centraliza a execução sequencial das estratégias de scraping
para uma determinada URL. A cada tentativa bem sucedida de coleta os dados
são validados e métricas de observabilidade são atualizadas.
"""

from typing import Callable, Literal
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
    ) -> None:
        """ Define dependências opcionais para o orquestrador

        ``strategy_selector`` permite injetar uma função customizada que
        retorna as estratégias disponíveis para uma URL. ``validator`` é
        utilizado para conferir a qualidade dos dados retornados.
        ``strategy_timeout`` define o tempo máximo para execução
        de cada estratégia.
        """
        self._strategy_selector = strategy_selector or strategies_for
        self._validator = validator or DataQualityValidator()
        self._strategy_timeout = strategy_timeout

    async def scrape(
        self,
        *,
        url: str,
        user_id: UUID,
        payload,
        product_type: Literal["monitored", "competitor"],
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None,
    ) -> dict:
        """ Executa as estratégias de scraping até obter um resultado válido

        As estratégias são recuperadas via :func:`strategies_for` e
        executadas em sequência. Cada execução é limitada por
        ``strategy_timeout`` através de ``asyncio.wait_for``. Ao
        final de cada tentativa a métrica ``SCRAPER_STRATEGY_TOTAL``
        registra estratégia utilizada e o status obtido.
        """
        strategies = self._strategy_selector(url)
        if not strategies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL não suportada",
            )

        result: dict = {"status": "error"}
        for idx, strategy in enumerate(strategies):
            if not strategy.supports_url(url):
                continue

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
                    ),
                    timeout=self._strategy_timeout,
                )
                status_label = result.get("status", "error")
            except asyncio.TimeoutError:
                #Tempo excedido: marca como falha e registra aviso
                logger.warning(
                    "strategy_timeout", strategy=strategy.__class__.__name__
                )
                result = {"status": "error"}
                status_label = "timeout"
            except Exception as err:
                #Registra o erro para facilitar diagnóstico no scraping
                logger.exception("unexpected_error_strategy", erro=(err))
                #Qualquer exceção marca a execução como erro
                result = {"status": "error"}
                status_label = "exception"

            details = result.get("details")
            if details is not None:
                try:
                    #Valida dados essenciais mesmo quando o dicionário está vazio, antes de aceitar o resultado
                    self._validator.validate(details)
                except ValueError:
                    #Dados inválidos: registra status e prepara fallback
                    status_label = "invalid"
                    result = {"status": "error"}

            #Registra a execução da estratégia com o status obtido
            SCRAPER_STRATEGY_TOTAL.labels(
                strategy.__class__.__name__, status_label
            ).inc()

            if status_label in ("success", "NOT_MODIFIED"):
                break

            #Caso o resultado não seja aproveitável, registra fallback
            if idx < len(strategies) - 1:
                SCRAPER_FALLBACK_TOTAL.inc()

        return result

__all__ = ["MultiStrategyScraperOrchestrator"]
