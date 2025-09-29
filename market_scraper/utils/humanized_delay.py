from __future__ import annotations

""" Utilitário para calcular atrasos de comportamento humano """

import asyncio
import random
import time

from market_scraper.core.config_scraper import settings


class HumanizedDelayManager:
    """ Calcula atrasos dinâmicos para simulação de navegação humana 
    
    O gerenciador combina tempo de leitura estimado, pequenas pausas de
    reflexão e um fator de fadiga aleatório para variar o ritmo das
    requisições e mitigar bloqueios por comportamento robótico.
    """
    def __init__(
        self,
        avg_wpm: int | float = settings.HUMAN_AVG_WPM,
        base_delay: float = settings.HUMAN_BASE_DELAY,
        fatigue_range: tuple[float, float] = (
            settings.HUMAN_FATIGUE_MIN,
            settings.HUMAN_FATIGUE_MAX,
        ),
    ) -> None:
        self.avg_wpm = avg_wpm
        self.base_delay = base_delay
        self.fatigue_min, self.fatigue_max = fatigue_range

    def calculate_delay(self, text: str | None, reflection_time: float = 1.0) -> float:
        """ Retorna um delay em segundos considerando tamanho do texto e aleatoriedade """
        words = len(text.split()) if text else 0
        reading_time = (words / float(self.avg_wpm)) * 60.0
        fatigue = random.uniform(self.fatigue_min, self.fatigue_max)
        return self.base_delay + reflection_time + reading_time + fatigue

    def wait(self, text: str | None, reflection_time: float = 1.0) -> None:
        """ Bloqueia o fluxo pelo tempo calculado de forma síncrona """
        delay = self.calculate_delay(text, reflection_time)
        time.sleep(delay)

    async def wait_async(self, text: str | None, reflection_time: float = 1.0) -> None:
        """ Aguarda de forma assíncrona o tempo calculado para a interação """
        delay = self.calculate_delay(text, reflection_time)
        await asyncio.sleep(delay)

    def prolong(self, factor: float = 1.5) -> None:
        """ Aumenta o delay base pelo *factor* para reduzir o ritmo de scraping """
        self.base_delay *= factor
