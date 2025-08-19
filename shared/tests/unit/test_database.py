""" Teste para módulo de banco de dados utilizando SQLite em memória """

import importlib
from sqlalchemy import text
from shared.metrics.metrics_db import DB_POOL_CHECKOUTS, DB_POOL_SIZE

def _recarregar_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory")
    from shared.infra.db import database
    return importlib.reload(database)

def test_get_engine(monkeypatch):
    db = _recarregar_db(monkeypatch)
    engine = db.get_engine()

    with engine.connect() as conn:
        resultado = conn.execute(text("SELECT 1")).scalar()

    assert resultado == 1
    assert isinstance(DB_POOL_SIZE._value.get(), float)

def test_get_db(monkeypatch):
    db = _recarregar_db(monkeypatch)
    gerador = db.get_db()
    sessao = next(gerador)

    conexao = sessao.connection()
    assert conexao.closed is False

    gerador.close()
    assert conexao.closed is True
    assert isinstance(DB_POOL_CHECKOUTS._value.get(), float)
