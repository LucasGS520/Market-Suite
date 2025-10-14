""" Validações de qualidade de dados para os resultados dos parsers """

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import structlog

from shared.metrics.metrics_scraper import SCRAPER_STEP_INVALID_TOTAL

from market_scraper.core.config_scraper import settings
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
    candidate = ""
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

def _extract_domain(candidate: str, fallback: str) -> str:
    """ Reduz URLs completas a hostname para uso em métricas de baixa cardinalidade """
    parsed = urlparse(candidate)
    hostname = parsed.hostname or parsed.netloc
    if hostname:
        return hostname
    return fallback

def _sanitize_decimal(value: str) -> Decimal | None:
    """ Converte strings numétricas simples em ``Decimal`` sem levantar exceções """
    try:
        return Decimal(value.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None

class DataQualityValidator:
    """ Aplica regras mínimas para garantir que o payload contenha dados úteis """
    _APPROX_PATTERN = re.compile(r"[-+]?[0-9]+(?:[\.,][0-9]+)?")

    def __init__(self, *, price_tolerance: float | Decimal | None = None) -> None:
        """ Inicializa o validador com tolerância opcional para preços aproximados """
        tolerance_source = price_tolerance
        if tolerance_source is None:
            tolerance_source = settings.SCRAPER_PRICE_TOLERANCE
        try:
            parsed = Decimal(str(tolerance_source))
        except (InvalidOperation, ValueError):
            parsed = Decimal("0")
        if parsed < 0:
            parsed = Decimal("0")
        self._price_tolerance = parsed
    
    def validate(
        self,
        *,
        step_name: str,
        payload: Mapping[str, Any] | None,
        url: str,
        source: str,
    ) -> dict[str, str] | None:
        """ Verifica chaves obrigatórias e normaliza preço e metadados """
        domain = _extract_domain(source, source)
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
            tolerant_price = self._try_tolerant_price(price_raw)
            if tolerant_price is None:
                #Registramos o problema e abortamos a etapa; fallback para próxima etapa
                self._register_invalid(step_name, domain, "price_invalid")
                return None
            price_decimal = tolerant_price
        
        normalized_payload = {
            "name": name,
            "current_price": format_decimal_to_str(price_decimal),
            "url": _normalize_url(payload.get("url"), url),
            "source": _normalize_source(payload.get("source"), source),
        }
        return normalized_payload
    
    def _register_invalid(self, step_name: str, domain: str, reason: str) -> None:
        """ Registra métrica e log estruturado para depuração """
        #Utilizamos labels nomeados para evitar erros em futuras mudanças de ordem
        SCRAPER_STEP_INVALID_TOTAL.labels(
            step=step_name,
            domain=domain,
            result=reason,
        ).inc()
        logger.warning(
            "step_invalid_result",
            step=step_name,
            domain=domain,
            result=reason,
            duration_ms=0.0,
        )

    def _try_tolerant_price(self, price_raw: Any) -> Decimal | None:
        """ Tenta interpretar preços aproximados respeitando a tolerância configurada """
        if self._price_tolerance <= 0:
            return None
        
        if isinstance(price_raw, (int, float, Decimal)):
            #Valores numéricos já são aceitos mesmo quando parse_price_str falha
            return Decimal(str(price_raw))
        
        if not isinstance(price_raw, str):
            return None
        
        matches = self._APPROX_PATTERN.findall(price_raw)
        if not matches:
            return None
        
        candidates: list[Decimal] = []
        for match in matches:
            candidate = _sanitize_decimal(match)
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            return None
        
        reference = candidates[0]
        if len(candidates) == 1:
            return reference
        
        #Aceita o valor quando os candidatos estão próximos entre si
        for candidate in self._iter_comparables(candidates[1:]):
            if candidate is None:
                return None
            if reference == 0:
                if abs(candidate) <= self._price_tolerance:
                    return reference
            else:
                delta = abs(candidate - reference) / abs(reference)
                if delta <= self._price_tolerance:
                    return reference
        return None
    
    @staticmethod
    def _iter_comparables(candidates: Iterable[Decimal]) -> Iterable[Decimal | None]:
        """ Gera valores comparáveis ao preço de referência ignorando inválidos """
        for candidate in candidates:
            try:
                yield Decimal(candidate)
            except (InvalidOperation, ValueError):
                yield None

__all__ = ["DataQualityValidator"]
