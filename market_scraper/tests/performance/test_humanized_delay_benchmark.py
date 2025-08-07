from scraper_app.utils.humanized_delay import HumanizedDelayManager


def test_calculate_delay_performance(benchmark, monkeypatch):
    monkeypatch.setattr("random.uniform", lambda a, b: 0.2)
    manager = HumanizedDelayManager(avg_wpm=200, base_delay=1.0, fatigue_range=(0.1, 0.3))
    text = "hello world" * 50
    benchmark(manager.calculate_delay, text, 0.5)
