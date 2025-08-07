from __future__ import annotations

""" Utilitário para calcular atrasos de comportamento humano """

import random
import time

from scraper_app.core.config import settings


class HumanizedDelayManager:
    """ Calcula atrasos dinâmicos para simulação de navegação humana """

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
        """ Aguarda o tempo calculado de forma síncrona """
        delay = self.calculate_delay(text, reflection_time)
        time.sleep(delay)

    def prolong(self, factor: float = 1.5) -> None:
        """ Aumenta o delay base pelo *factor* para reduzir o ritmo de scraping """
        self.base_delay *= factor
