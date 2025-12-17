""" Validações de qualidade de dados para os resultados dos parsers 

O módulo concentra o ``DataQualityValidator`` utilizado pelo pipeline
do scraper e funções auxiliares responsáveis por justificar as decisões
de rejeição.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import structlog

from shared.utils.logging_utils import sanitize_log_data
from shared.utils.url_validation import normalize_product_url
from shared.metrics.metrics_scraper import (
    SCRAPER_AVAILABILITY_HEURISTICS_TOTAL,
    SCRAPER_STEP_INVALID_TOTAL,
    SCRAPER_VALIDATION_REJECT_TOTAL,
)

from market_scraper.core.config_scraper import settings
from market_scraper.utils.price import format_decimal_to_str, parse_price_str


logger = structlog.get_logger("data_quality_validator")

@dataclass(frozen=True)
class ValidationResult:
    """ Representa a decisão produzida pelo ``DataQualityValidator`` """
    payload: dict[str, str] | None
    reason_code: str | None = None
    reason_message: str | None = None

    @property
    def is_valid(self) -> bool:
        """ Indica se o payload foi aceito pela validação de qualidade """
        return self.payload is not None

def _normalize_url(raw_url: Any, fallback: str) -> str:
    """ Padroniza URL de saída priorizando o valor válido do contexto """
    candidate = ""
    if isinstance(raw_url, str):
        candidate = raw_url.strip()
    elif raw_url is not None:
        #Convertendo outros tipos para string evitando propagar objetos inesperados
        candidate = str(raw_url).strip()

    if candidate:
        try:
            #Reutilizamos a normalização compartilhada para alinhar regras entre serviços
            return normalize_product_url(candidate)
        except ValueError:
            #Quando o parser produz um valor ilegítimo usamos o fallback confiável
            pass

    try:
        return normalize_product_url(fallback)
    except ValueError:
        #Garante que valores residuais não contaminem payload final
        return str(fallback or "")

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
    _REASON_MESSAGES = {
        "payload_empty": "Payload ausente ou vazio",
        "name_missing": "Campo name ausente ou vazio",
        "price_invalid": "Preço ausente ou inválido",
    }

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
        parser_name: str | None = None,
        dump_path: str | None = None,
    ) -> ValidationResult:
        """ Verifica chaves obrigatórias e normaliza preço e metadados """
        domain = _extract_domain(source, source)
        if not payload:
            reason_code = "payload_empty"
            reason_message = self._REASON_MESSAGES[reason_code]
            self._register_invalid(
                step_name,
                domain,
                reason_code,
                reason_message,
                url,
                parser_name,
                dump_path,
            )
            return ValidationResult(payload=None, reason_code=reason_code, reason_message=reason_message)
        
        name = str(payload.get("name", "")).strip()
        if not name:
            reason_code = "name_missing"
            reason_message = self._REASON_MESSAGES[reason_code]
            self._register_invalid(
                step_name,
                domain,
                reason_code,
                reason_message,
                url,
                parser_name,
                dump_path,
            )
            return ValidationResult(payload=None, reason_code=reason_code, reason_message=reason_message)
        
        price_raw = payload.get("current_price")
        availability = payload.get("availability")
        price_decimal = None
        if availability is False:
            SCRAPER_AVAILABILITY_HEURISTICS_TOTAL.labels(reason="unavailable_payload").inc()
        else:
            try:
                price_decimal = parse_price_str(price_raw, url)
            except ValueError:
                tolerant_price = self._try_tolerant_price(price_raw)
                if tolerant_price is None:
                    #Registramos o problema e abortamos a etapa; fallback para próxima etapa
                    reason_code = "price_invalid"
                    reason_message = self._REASON_MESSAGES[reason_code]
                    self._register_invalid(
                        step_name,
                        domain,
                        reason_code,
                        reason_message,
                        url,
                        parser_name,
                        dump_path,
                    )
                    return ValidationResult(payload=None, reason_code=reason_code, reason_message=reason_message)
                price_decimal = tolerant_price
            if price_decimal is not None and price_decimal == 0:
                SCRAPER_AVAILABILITY_HEURISTICS_TOTAL.labels(reason="zero_price_filtered").inc()
                price_decimal = None
        
        normalized_url = _normalize_url(payload.get("url"), url)
        canonical_source = _extract_domain(normalized_url, source)
        normalized_payload = {
            "name": name,
            "current_price": format_decimal_to_str(price_decimal) if price_decimal is not None else None,
            "url": normalized_url,
            "source": _normalize_source(payload.get("source"), canonical_source),
            "availability": availability if isinstance(availability, bool) else None,
            "last_status": payload.get("last_status"),
            "currency": payload.get("currency"),
        }
        return ValidationResult(payload=normalized_payload)
    
    def _register_invalid(
        self,
        step_name: str,
        domain: str,
        reason_code: str,
        reason_message: str,
        url: str,
        parser_name: str | None = None,
        dump_path: str | None = None,
    ) -> None:
        """ Registra métrica e log estruturado para depuração """
        #Utilizamos labels nomeados para evitar erros em futuras mudanças de ordem
        SCRAPER_STEP_INVALID_TOTAL.labels(
            step=step_name,
            domain=domain,
            result=reason_code,
        ).inc()
        SCRAPER_VALIDATION_REJECT_TOTAL.labels(
            domain=domain,
            step=step_name,
            reason=reason_code,
        ).inc()
        logger.warning(
            "validation_rejected_payload",
            step=step_name,
            domain=domain,
            reason_code=reason_code,
            reason_message=reason_message,
            url=sanitize_log_data(url),
            parser_name=parser_name or "unknown",
            dump_path=dump_path,
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

__all__ = ["DataQualityValidator", "ValidationResult"]
