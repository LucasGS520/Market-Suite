"""Configuração de engine e sessões com SQLAlchemy.

Este módulo cria o engine do SQLAlchemy e a fábrica de sessões que será
utilizada por toda a aplicação. também define funções utilitárias e eventos
para instrumentação do pool de conexões
"""

import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from alert_app.core.config import settings
import alert_app.metrics as metrics


#Exibe as queries SQL no console quando a variável DEBUG está habilitada
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

#Criação do engine que gerencia as conexões com o banco de dados
engine = create_engine(settings.DATABASE_URL, echo=DEBUG, pool_pre_ping=True)

#Configurando sessões de banco de Dados
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ---------- Instrumentação do pool de conexões ----------
@event.listens_for(engine, "connect")
def connect(dbapi_conn, connection_record):
    """ Atualiza o tamanho do pool a cada nova conexão """
    try:
        metrics.DB_POOL_SIZE.set(engine.pool.size())
    except Exception:
        pass

@event.listens_for(engine, "checkout")
def checkout(dbapi_conn, connection_record, connection_proxy):
    """ Registra o número de conexões ativas """
    try:
        metrics.DB_POOL_CHECKOUTS.set(engine.pool.checkedout())
    except Exception:
        pass

@event.listens_for(engine, "checkin")
def checkin(dbapi_conn, connection_record):
    """ Atualiza o contador quando a conexão é devolvida ao pool """
    try:
        metrics.DB_POOL_CHECKOUTS.set(engine.pool.checkedout())
    except Exception:
        pass


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
