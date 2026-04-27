""" Interface pública do orquestrador de scraping.

ScraperOrchestrator encapsula o ParseProduct e expõe métodos de alto nível
para consumidores externos (routes, testes de integração).
"""

from __future__ import annotations

from typing import Any

from structlog.stdlib import BoundLogger

from market_scraper.scraper_orchestrator.parse_product import (
    ParseProduct,
    ParseProductError,
    ParseProductNoResult,
    ParseProductResult,
    ParseProductSuccess,
)
from market_scraper.infra.logging.structured_logger import get_scraper_logger

logger = get_scraper_logger("scraper_orchestrator")


class ScraperOrchestrator:
    """Fachada pública do pipeline de scraping.

    Encapsula o caso de uso ParseProduct e provê métodos de alto nível
    para que as rotas HTTP não conheçam detalhes internos do fluxo.
    """

    def __init__(self) -> None:
        self._use_case = ParseProduct()

    async def parse_product(
        self,
        url: str,
        *,
        metadata: dict[str, Any] | None = None,
        request_logger: BoundLogger | None = None,
        force_refresh: bool = False,
        trace_id: str | None = None,
    ) -> ParseProductResult:
        """Executa o pipeline completo para a URL e retorna resultado tipado.

        Args:
            url: URL canônica do produto.
            metadata: Metadados opcionais de correlação (trace_id, monitored_id, etc.).
            request_logger: Logger com contexto da requisição; usa logger padrão se None.
            force_refresh: Quando True, ignora cache e força nova coleta.
            trace_id: Identificador de rastreamento; extraído de metadata se ausente.

        Returns:
            ParseProductResult — discriminated union de Success / NoResult / Error.
        """
        effective_logger = request_logger or logger
        effective_trace_id = trace_id or (
            str(metadata.get("trace_id")) if metadata else None
        )
        effective_force_refresh = force_refresh or bool(
            metadata.get("force_refresh") if metadata else False
        )

        return await self._use_case.execute(
            url,
            request_logger=effective_logger,
            force_refresh=effective_force_refresh,
            trace_id=effective_trace_id,
        )

    async def health_check(self) -> dict[str, str]:
        """Retorna estado básico do orquestrador para o endpoint /health."""
        return {"orchestrator": "ok"}


def get_scraper_orchestrator() -> ScraperOrchestrator:
    """Retorna instância de ScraperOrchestrator (criada a cada chamada; stateless)."""
    return ScraperOrchestrator()


__all__ = [
    "ScraperOrchestrator",
    "get_scraper_orchestrator",
]
