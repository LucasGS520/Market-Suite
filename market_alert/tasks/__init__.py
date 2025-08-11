"""Registro de tasks Celery utilizadas na aplicação."""

from market_alert.core.celery_app import celery_app

#As tasks são registradas via ''include'' em ''market_alert.core.celery_app''
#Evitamos importar submódulos aqui para não executar código pesado
#como inicialização de RateLimiter durante a simples importação
#do pacote ''market_alert.tasks'' em testes ou outros módulos

__all__ = ("celery_app",)
