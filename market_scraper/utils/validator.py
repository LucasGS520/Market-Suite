""" Validações de qualidade de dados para os resultados dos parsers """

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse

import structlog

from shared.metrics.metrics_scraper import SCRAPER_STEP_INVALID_TOTAL

from market_scraper.utils.price import format_decimal_to_str, parse_price_str


logger = structlog.get_logger("data_quality_validator")

def _normalize_url(raw_url: Any, fallback: str) -> str:
    """ Padroniza URL de saída priorizando o valor válido do contexto """
    if isinstance(raw_url, str):
        candidate = raw_url.strip()
        if candidate:
            return candidate
    return fallback

def _normalize_source(raw_source: Any, fallback: str) -> str:
    """ Garante que a origem represente um domínio válido """
    condidate = ""
    #Inicializamos o valor para evitar erros quando a origem não estiver presente no payload
    if isinstance(raw_source, str):
        candidate = raw_source.strip()
    elif raw_source is not None:
        candidate = str(raw_source).strip()

    if candidate:
        parsed = urlparse(candidate)
        hostname = parsed.hostname or parsed.netloc
        if hostname:
            return hostname
        if " " not in candidate and "." in candidate:
            return candidate
    return fallback

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
        domain = source
        if not payload:
            self._register_invalid(step_name, domain, "payload_empty")
            return None
        
        name = str(payload.get("name", "")).strip()
        if not name:
            self._register_invalid(step_name, domain, "name_missing")
            return None
        
        price_raw = payload.get("current_price")
        try:
            price_decimal = parse_price_str(price_raw, url)
        except ValueError:
            #Registramos o problema e abortamos a etapa; fallback para próxima etapa
            self._register_invalid(step_name, domain, "price_invalid")
            return None
        
        normalized_payload = {
            "name": name,
            "current_price": format_decimal_to_str(price_decimal),
            "url": _normalize_url(payload.get("url"), url),
            "source": _normalize_source(payload.get("source"), source),
        }
        return normalized_payload
    
    def _register_invalid(self, step_name: str, domain: str, reason: str) -> None:
        """ Registra métrica e log estruturado para depuração """
        SCRAPER_STEP_INVALID_TOTAL.labels(step_name, domain, reason).inc()
        logger.warning(
            "step_invalid_result",
            step=step_name,
            domain=domain,
            result=reason,
            duration_ms=0.0,
        )

__all__ = ["DataQualityValidator"]
