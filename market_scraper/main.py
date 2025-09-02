""" Ponto de entrada da aplicação FastAPI do serviço de scraping

Este módulo cria uma instância principal do FastAPI e registra as rotas
expostas pelo serviço
"""

from fastapi import FastAPI

try:
    #Importação relativa quando executado como parte do pacote
    from .routes import routes_health, routes_scraper
except ImportError:
    #Fallaback para execução direta a partir do diretório do serviço
    from routes import routes_health, routes_scraper

#Instância principal do aplicativo FastAPI
app = FastAPI(title="MarketScraper")

#Registro das rotas de saúde e de scraping
app.include_router(routes_health.router)
#Disponibiliza o endpoint com dois prefixos por compatibilidade ("/scraper" e "/scrape")
app.include_router(routes_scraper.router, prefix="/scraper")
app.include_router(routes_scraper.router, prefix="/scrape")

#A variável `app` é exposta para uso pelo Uvicorn
__all__ = ["app"]
