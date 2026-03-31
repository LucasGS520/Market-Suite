"""Módulo de dispatch/enfileiramento de coletas dos produtos.

Responsabilidade: construir payloads tipados (CollectionPayload) e enfileirar
coletas na fila Celery 'scraping'. Não contém lógica de negócio nem I/O de
scraping — apenas montagem de payload e envio à fila.

Expõe apenas interfaces estáveis para consumidores externos.
"""

__all__: list[str] = []
