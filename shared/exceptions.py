""" Exceções compartilhadas entre os serviços

Este utilitário é reutilizado por `market_alert` e `market_scraper` para
padronizar erros de scraping serializáveis pelo Celery
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
