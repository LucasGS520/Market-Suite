""" Ponto de entrada da aplicação FastAPI do serviço de scraping

Este módulo cria uma instância principal do FastAPI e registra as rotas
expostas pelo serviço
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

#Importação relativa para execução como pacote
from .routes import routes_health, routes_scraper

#Instância principal do aplicativo FastAPI
app = FastAPI(title="MarketScraper")

#Manipulador para erros de validação da requisição
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """ Retorna mensagem amigável quando a URL é inválida """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "URL inválida ou malformada"},
    )

#Registro das rotas de saúde e de scraping
app.include_router(routes_health.router)
#Disponibiliza o endpoint com dois prefixos por compatibilidade ("/scraper" e "/scrape")
app.include_router(routes_scraper.router, prefix="/scraper")
app.include_router(routes_scraper.router, prefix="/scrape")

#A variável `app` é exposta para uso pelo Uvicorn
__all__ = ["app"]
