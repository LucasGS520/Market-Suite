""" Validações de qualidade de dados para os resultados dos parsers """

from __future__ import annotations

from typing import Any, Mapping

import structlog

from shared.metrics.metrics_scraper import SCRAPER_STEP_INVALID_TOTAL

from market_scraper.utils.price import format_decimal_to_str, parse_price_str


logger = structlog.get_logger("data_quality_validator")

class DataQualityValidator:
    """ Aplica regras mínimas para garantir que o payload contenha dados úteis """
    def validate(
        self,
        *,
        step_name: str,
        payload: Mapping[str, Any] | None,
        url: str,
        source: str,
    ) -> dict[str, str] | None:
        """ Verifica chaves obrigatórias e normaliza preço e metadados """
        if not payload:
            self._register_invalid(step_name, source, "payload_empty")
            return None
        
        name = str(payload.get("name", "")).strip()
        if not name:
            self._register_invalid(step_name, source, "name_missing")
            return None
        
        price_raw = payload.get("current_price")
        try:
            price_decimal = parse_price_str(price_raw, url)
        except ValueError:
            #Registramos o problema e abortamos a etapa; fallback para próxima etapa
            self._register_invalid(step_name, source, "price_invalid")
            return None
        
        normalized_payload = {
            "name": name,
            "current_price": format_decimal_to_str(price_decimal),
            "url": str(payload.get("url") or url).strip() or url,
            "source": str(payload.get("source") or source).strip() or source,
        }
        return normalized_payload
    
    def _register_invalid(self, step_name: str, source: str, reason: str) -> None:
        """ Registra métrica e log estruturado para depuração """
        SCRAPER_STEP_INVALID_TOTAL.labels(step_name, source).inc()
        logger.warning(
            "step_invalid_result",
            step=step_name,
            source=source,
            reason=reason,
        )

__all__ = ["DataQualityValidator"]
