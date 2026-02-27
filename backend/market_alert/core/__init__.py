"""Camada core do ``market_alert``.

Esta camada concentra contratos e regras centrais da aplicação.
Para manter fronteiras claras, implementações que dependem de tecnologia
externa (Redis, Celery, FastAPI, banco etc.) devem residir em
``market_alert.infraestructure``.
"""
