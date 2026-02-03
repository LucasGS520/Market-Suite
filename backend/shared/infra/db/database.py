"""Configuração de engine e sessões com SQLAlchemy.

Este módulo cria o engine do SQLAlchemy e a fábrica de sessões que será
utilizada por toda a aplicação. também define funções utilitárias e eventos
para instrumentação do pool de conexões
"""

import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from shared.core.config_base import ConfigBase


class DBSettings(ConfigBase):
    """ Configurações mínimas para acesso ao banco de dados """
    DATABASE_URL: str = os.getenv("DATABASE_URL")

_settings = DBSettings()

#Exibe as queries SQL no console quando a variável DEBUG está habilitada
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

#Criação do engine que gerencia as conexões com o banco de dados
engine = create_engine(_settings.DATABASE_URL, echo=DEBUG, pool_pre_ping=True)

#Configurando sessões de banco de Dados
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------- Função para obter a sessão do banco de dados para cada requisição ----------
def get_db() -> Generator:
    """ Gera uma sessão de banco garantindo seu fechamento """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


#Função para obter o engine do banco de dados
def get_engine():
    """ Retorna a instância bruta do engine """
    return engine
