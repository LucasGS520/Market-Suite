class ScraperError(Exception):
    """ Erro levantado durante tarefas de scraping """
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")

    def __reduce__(self):
        """ Torna a exception selecionável para serialização do Celery """
        return (self.__class__, (self.status_code, self.detail))
