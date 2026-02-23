""" Camada de domínio do market_alert.

Centraliza regras de negócio puras para o ciclo de vida de produtos:
agendamento, transições de status, rastreamento de preço e estabilidade.

Regras desta camada:
- Não importa de: services, crud, orchestrator, tasks, Redis, FastAPI
- Não acessa banco de dados nem filas
- Funções recebem objetos de modelo e retornam decisões/mutações sem commit
"""
