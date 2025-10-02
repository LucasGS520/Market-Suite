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
