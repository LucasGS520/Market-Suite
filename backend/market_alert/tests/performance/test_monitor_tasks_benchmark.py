import asyncio
import time
from types import SimpleNamespace

from backend.market_alert.tasks import monitor_recheck_tasks


def test_parse_monitored_batch_benchmark(benchmark, monkeypatch):
    #Cria objetos simples simulando produtos a serem processados
    batch = [SimpleNamespace(id=i, product_url=f"http://exemplo.com/{i}") for i in range(3)]

    async def fake_parse(url: str, product_type: str, **k):
        #Simula atraso de rede para testar concorrência
        await asyncio.sleep(0.1)
        return {"current_price": 10.0, "thumbnail": None, "free_shipping": False}

    #Substitui o cliente real por uma versão simulada
    monkeypatch.setattr(monitor_recheck_tasks, "scraper_client", SimpleNamespace(parse=fake_parse))

    def run():
        start = time.perf_counter()
        asyncio.run(monitor_recheck_tasks._parse_monitored_batch(batch))
        return time.perf_counter() - start

    tempo_execucao = benchmark(run)
    #Se as tarefas rodarem em paralelo, o tempo deve ser inferior à soma sequencial
    assert tempo_execucao < 0.25

def test_parse_competitor_batch_benchmark(benchmark, monkeypatch):
    """ Verifica processamento paralelo para lotes de concorrentes """

    #Cria objetos simples simulando concorrentes a serem processados
    batch = [SimpleNamespace(id=i, product_url=f"http://exemplo.com/{i}") for i in range(3)]

    async def fake_parse(url: str, product_type: str, **k):
        #Simula atraso de rede para testar concorrência
        await asyncio.sleep(0.1)
        return {"current_price": 10.0, "thumbnail": None, "free_shipping": False}

    #Substitui o cliente real por uma versão simulada
    monkeypatch.setattr(monitor_recheck_tasks, "scraper_client", SimpleNamespace(parse=fake_parse))

    def run():
        start = time.perf_counter()
        asyncio.run(monitor_recheck_tasks._parse_competitor_batch(batch))
        return time.perf_counter() - start

    tempo_execucao = benchmark(run)
    #Se as tarefas rodarem em paralelo, o tempo deve ser inferior à soma sequencial
    assert tempo_execucao < 0.25
