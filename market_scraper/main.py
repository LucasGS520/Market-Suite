""" Ponto de entrada da aplicação FastAPI do serviço de scraping

Este módulo cria uma instância principal do FastAPI e registra as rotas
expostas pelo serviço
"""

from fastapi import FastAPI

from market_scraper.routes import routes_health, routes_scraper


#Instância principal do aplicativo FastAPI
app = FastAPI(title="MarketScraper")

#Registro das rotas de saúde e de scraping
app.include_router(routes_health.router)
app.include_router(routes_scraper.router)

#A variável `app` é exposta para uso pelo Uvicorn
__all__ = ["app"]
