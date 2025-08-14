""" Inicializa o pacote de banco de dados compartilhado

Reexporta utilidades de sessão e engine para uso nos demais módulos
"""

from .base import Base
from .database import SessionLocal, get_db, get_engine, engine

#Define o que é exportado ao utilizar "from shared.infra.db import *"
__all__ = ["Base", "SessionLocal", "get_db", "get_engine", "engine"]
