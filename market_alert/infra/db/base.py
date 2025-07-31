""" Camada base de modelos da aplicação

Este módulo define a classe Base que serve como base para todos
os modelos SQLAlchemy utilizados no projeto.
A partir dela, todos os modelos de persistência herdam
funcionalidades comuns e configurações de metadados
"""

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """ Classe base para todos os modelos SQLAlchemy """
    pass
