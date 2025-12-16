""" Testes de normalização e gravação do histórico de preços. """

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from market_alert.crud import crud_price_history


class QueryStub:
    """ Simula operações de query para retornar nenhum resultado """
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return None


class DummySession:
    """ Sessão simulada para validar comportamento sem banco real """
    def __init__(self):
        self.added = []
        self.flushed = False

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed = True

    def query(self, model):
        return QueryStub()


def test_create_for_monitored_normalizes_naive_datetime():
    """ Garante que timestamps sem timezone são convertidos para UTC """
    db = DummySession()
    naive_checked_at = datetime(2024, 1, 1, 12, 0, 0)

    entry = crud_price_history.create_for_monitored(
        db,
        uuid4(),
        Decimal("10.50"),
        "BRL",
        naive_checked_at,
    )

    assert entry.checked_at == naive_checked_at.replace(tzinfo=timezone.utc)
    assert entry.checked_at.tzinfo == timezone.utc
    assert db.flushed is True


def test_create_for_competitor_normalizes_aware_datetime():
    """ Confere que timestamps com offset são convertidos corretamente para UTC """
    db = DummySession()
    aware_checked_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=-3)))

    entry = crud_price_history.create_for_competitor(
        db,
        uuid4(),
        Decimal("21.90"),
        "BRL",
        aware_checked_at,
    )

    assert entry.checked_at == aware_checked_at.astimezone(timezone.utc)
    assert entry.checked_at.tzinfo == timezone.utc
    assert db.flushed is True
