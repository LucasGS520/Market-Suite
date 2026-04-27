"""Infraestrutura de logging estruturado para o market_scraper."""

from market_scraper.infra.logging.structured_logger import (
    bind_request_context,
    bind_stage_context,
    get_scraper_logger,
)

__all__ = ["get_scraper_logger", "bind_request_context", "bind_stage_context"]
