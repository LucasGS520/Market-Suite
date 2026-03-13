""" Exceções compartilhadas entre os serviços

Este utilitário é reutilizado por `market_alert`, `market_orchestrator` e `market_scraper` para
padronizar erros de scraping ou orquestração serializáveis.
"""

class TemporalUnavailableError(Exception):
    """ Levantada quando o Temporal Server não está acessível.

    Deve ser capturada no cliente adaptador e logada como warning/error
    sem propagar para o chamador (fallback não-bloqueante).
    """

class ScraperError(Exception):
    """ Erro levantado durante tarefas de scraping """
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")

    def __reduce__(self):
        """ Torna a exceção serializável do Celery """
        return (self.__class__, (self.status_code, self.detail))
