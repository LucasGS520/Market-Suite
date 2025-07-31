from __future__ import annotations

""" Gerencia o agendamento adaptativo de novas coletas

Este módulo calcula quando cada produto deve ser rechecado levando em conta
histórico de falhas e dinâmica de preços. Os horários são armazenados em Redis
e utilizados pelas tasks para priorizar as coletas.
"""

import random
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any

import app.utils.redis_client as _rc
from app.metrics import RECHECK_SCHEDULED_TOTAL


class AdaptiveRecheckManager:
    """ Calcula os próximos horários de coleta considerando preços e falhas """

    def __init__(
            self,
            base_interval: int = 600,
            min_interval: int = 120,
            max_interval: int = 3600,
            peak_hours: tuple[int, int] = (18, 22),
            jitter: float = 0.1
    ) -> None:
        self.redis = _rc.get_redis_client()
        self.base_interval = float(base_interval)
        self.min_interval = float(min_interval)
        self.max_interval = float(max_interval)
        self.peak_start, self.peak_end = peak_hours
        self.jitter = jitter

    def _next_key(self, identifier: str) -> str:
        """ Chave Redis onde armazena o próximo horário de coleta """
        return f"recheck:next:{identifier}"

    def _fail_key(self, identifier: str) -> str:
        """ Chave Redis onde registra o número de falhas consecutivas """
        return f"recheck:fail:{identifier}"

    def should_recheck(self, identifier: str) -> bool:
        """ Indica se já passou do horário agendado para nova coleta """
        raw = self.redis.get(self._next_key(identifier))
        if not raw:
            return True
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        next_time = datetime.fromisoformat(raw)
        return next_time <= datetime.now(timezone.utc)

    def record_result(self, identifier: str, success: bool) -> None:
        """ Atualiza o contador de falhas para o identificador informado """
        if success:
            self.redis.delete(self._fail_key(identifier))
        else:
            failures = int(self.redis.get(self._fail_key(identifier)) or 0) + 1
            self.redis.set(self._fail_key(identifier), failures, ex=86400)

    def schedule_next(self, product: Any, comparisons: Optional[List[Any]] = None) -> datetime:
        """ Calcula e armazena o próximo horário de scraping para o produto """
        identifier = str(product.id)

        interval = self.base_interval

        if comparisons:
            #Diminui o intervalo quando há alertas recentes
            latest = comparisons[0].data if comparisons else {}
            if latest.get("alerts"):
                interval *= 0.5

            target = getattr(product, "target_price", None)
            low = latest.get("lowest_competitor", {}).get("price")
            if target and low is not None:
                try:
                    target_d = Decimal(str(target))
                    low_d = Decimal(str(low))
                    if abs(low_d - target_d) <= target_d * Decimal("0.05"):
                        interval *= 0.7
                except Exception:
                    pass

            #Analisa a variação média de preços dos concorrentes
            avg_prices: List[Decimal] = []
            for cmp_ in comparisons[:3]:
                val = cmp_.data.get("average_competitor_price")
                if val is not None:
                    try:
                        avg_prices.append(Decimal(str(val)))
                    except Exception:
                        pass
            if len(avg_prices) >= 2:
                mean = sum(avg_prices) / len(avg_prices)
                spread = max(avg_prices) - min(avg_prices)
                if mean and spread > mean * Decimal("0.1"):
                    interval *= 0.7
                else:
                    interval *= 1.2

        hour = datetime.now(timezone.utc).hour
        if self.peak_start <= hour < self.peak_end:
            #Durante horário de pico, encurta o período de espera
            interval *= 0.7

        failures = int(self.redis.get(self._fail_key(identifier)) or 0)
        if failures:
            #Aplica backoff exponencial conforme o número de falhas
            interval *= 2 ** failures

        jitter_factor = 1 + random.uniform(-self.jitter, self.jitter)
        #Pequeno ruído para evitar sincronização perfeita
        interval *= jitter_factor

        interval = max(self.min_interval, min(interval, self.max_interval))
        next_time = datetime.now(timezone.utc) + timedelta(seconds=interval)
        #Persiste o horário calculado no Redis
        self.redis.set(self._next_key(identifier), next_time.isoformat())
        RECHECK_SCHEDULED_TOTAL.inc()
        return next_time
