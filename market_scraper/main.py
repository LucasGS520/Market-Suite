""" Ponto de entrada da aplicação FastAPI do serviço de scraping

O módulo cria a instância principal do FastAPI, registra as rotas
de saúde, scraping e expõe a rota de métricas compartilhada
com o restante da plataforma.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

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

@app.get("/metrics")
async def metrics_endpoint() -> Response:
    """ Expõe as métricas do ``DEFAULT_REGISTRY`` para coleta pelo Prometheus """
    payload = generate_latest(REGISTRY)
    #Retornamos a resposta diretamente para respeitar o contrato esperado pelo Prometheus
    return Response(payload, media_type=CONTENT_TYPE_LATEST)

#A variável `app` é exposta para uso pelo Uvicorn
__all__ = ["app"]
