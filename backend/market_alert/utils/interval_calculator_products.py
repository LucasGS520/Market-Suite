""" Utilitários para calcular estabilidade e intervalos de coleta.

O cálculo considera o histórico de mudanças de preço e o tempo desde a última
alteração relevante, permitindo ajustar dinamicamente a frequência de coleta.
Este módulo é a única fonte de verdade para o cálculo de estabilidade e 
intervalos, evitando duplicação de lógica em outras partes do sistema.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta

from market_alert.core.config_alert import settings
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import MonitoredProduct


STABILITY_UNSTABLE = 0
STABILITY_STABLE = 1
STABILITY_VERY_STABLE = 2

def _utc_now() -> datetime:
    """ Retorna timestamp em UTC sem microssegundos para logs """
    return datetime.now(timezone.utc).replace(microsecond=0)

def _resolve_next_check_at(
    monitored: MonitoredProduct,
    next_check_at: datetime | None,
) -> tuple[datetime, datetime]:
    """ Resolve o próximo check garantindo data válida e retorna também o horário base """
    now = _utc_now()
    resolved_next_check_at = next_check_at or monitored.next_check_at or now
    if resolved_next_check_at < now:
        #Evita reenqueue com horário no passado para impedir loops ociosos
        resolved_next_check_at = now
    return resolved_next_check_at, now

def _parse_next_retry_at(value: str | None) -> datetime | None:
    """ Converte string ISO de retry para datetime com timezone """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _normalize_datetime(value: datetime | None) -> datetime | None:
    """ Normaliza datas para UTC preservando valores nulos """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def calculate_stability_score(
    product: MonitoredProduct,
    *,
    reference_time: datetime | None = None,
) -> int:
    """ Calcula a pontuação de estabilidade baseada na última mudança registrada """
    now = _normalize_datetime(reference_time) or datetime.now(timezone.utc)

    #Prioriza mudanças explícitas, mas considera indicadores de grupo e criaão como fallback
    last_change = (
        product.last_price_change_at
        or product.group_collected_at
        or product.last_scraped_at
        or product.created_at
    )
    last_change = _normalize_datetime(last_change)

    if last_change is None:
        return STABILITY_UNSTABLE
    
    days_since_change = (now - last_change).total_seconds() / 86400

    if days_since_change >= settings.STABILITY_DAYS_VERY_STABLE:
        return STABILITY_VERY_STABLE
    if days_since_change >= settings.STABILITY_DAYS_STABLE:
        return STABILITY_STABLE
    return STABILITY_UNSTABLE

def _random_interval(min_seconds: int, max_seconds: int) -> int:
    """ Sorteia um intervalo entre limites """
    if min_seconds >= max_seconds:
        return min_seconds
    return random.randint(min_seconds, max_seconds)

def calculate_next_interval(
    product: MonitoredProduct,
    *,
    reference_time: datetime | None = None,
) -> int:
    """ Retorna o intervalo em segundos até a próxima coleta do produto """
    stability_score = calculate_stability_score(product, reference_time=reference_time)
    
    if stability_score == STABILITY_VERY_STABLE:
        return _random_interval(
            settings.COLLECT_INTERVAL_VERY_STABLE_MIN,
            settings.COLLECT_INTERVAL_VERY_STABLE_MAX
        )
    
    if stability_score == STABILITY_STABLE:
        return _random_interval(
            settings.COLLECT_INTERVAL_STABLE_MIN,
            settings.COLLECT_INTERVAL_STABLE_MAX,
        )
    
    return _random_interval(
        settings.COLLECT_INTERVAL_UNSTABLE_MIN,
        settings.COLLECT_INTERVAL_UNSTABLE_MAX,
    )

def calculate_next_check_at(
    product: MonitoredProduct,
    collected_at: datetime | None,
) -> datetime:
    """ Calcula o datetime da próxima coleta considerando o horário da extração """
    normalized_collected = _normalize_datetime(collected_at) or datetime.now(timezone.utc)
    if product.status == MonitoredStatus.pending and not product.last_checked:
        #Mantém o primeira coleta imediata para itens recém criados
        return normalized_collected
    interval_seconds = calculate_next_interval(product, reference_time=normalized_collected)
    return normalized_collected + timedelta(seconds=interval_seconds)

__all__ = [
    "STABILITY_UNSTABLE",
    "STABILITY_STABLE",
    "STABILITY_VERY_STABLE",
    "calculate_stability_score",
    "calculate_next_interval",
    "calculate_next_check_at",
    "_utc_now",
    "_resolve_next_check_at",
    "_parse_next_retry_at",
]
