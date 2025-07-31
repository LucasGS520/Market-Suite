import time
import pytest

from app.utils.humanized_delay import HumanizedDelayManager

def test_calculate_delay_range(monkeypatch):
    """ Verifica cálculo de delay para um texto grande """
    monkeypatch.setattr('random.uniform', lambda a, b: 0.2)
    dm = HumanizedDelayManager(avg_wpm=200, base_delay=1.0, fatigue_range=(0.1, 0.3))
    text = 'word ' * 200
    delay = dm.calculate_delay(text, reflection_time=0.5)
    assert 61.6 < delay < 61.8

def test_delay_variability(monkeypatch):
    """ Garante que delays sucessivos variam aleatoriamente """
    seq = [0.1, 0.2, 0.15]

    def fake_uniform(a, b):
        return seq.pop(0)

    monkeypatch.setattr('random.uniform', fake_uniform)
    dm = HumanizedDelayManager(avg_wpm=200, base_delay=1.0, fatigue_range=(0.1, 0.2))
    delays = [dm.calculate_delay('hello world', reflection_time=0) for _ in range(3)]
    assert len(set(delays)) == 3
