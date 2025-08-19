""" Fixtures e utilidades para testes de integração """

import pytest
import sys
from types import SimpleNamespace
from fastapi import FastAPI

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import uuid4

from shared.infra.db import Base
from shared.infra.db import get_db

from main import app
from market_alert.core.security import get_current_user
from market_alert.core.password import hash_password
from market_alert.models.models_users import User
from market_alert.tasks import scraper_tasks

#Utiliza banco SQLite em memória para testes
db_url = "sqlite:///:memory:"
if db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
else:
    engine = create_engine(db_url)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    """ Mocka Redis e cache para evitar conexões externas nos testes de integração """

    class FakeRedis:
        def get(self, *args, **kwargs): return None
        def set(self, *args, **kwargs): pass
        def exists(self, *args, **kwargs): return False
        def script_load(self, *args, **kwargs): return "mock_sha"
        def evalsha(self, *args, **kwargs): return 1

    class DummyCacheManager:
        def __init__(self):
            self.data = {}
        def get(self, url):
            return self.data.get(url)
        def get_data(self, url):
            return self.data.get(url)
        def set(self, url, data, content, etag=None):
            self.data[url] = data
        def invalidate(self, url):
            self.data.pop(url, None)

    #Substitui Redis_client nos serviços e Tasks
    fake_redis = FakeRedis()
    cache = DummyCacheManager()

    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("shared.utils.redis_client._thread_local", SimpleNamespace(client=fake_redis))
    monkeypatch.setattr("market_alert.services.services_scraper_monitored.redis_client", fake_redis, raising=False)
    monkeypatch.setattr("market_alert.services.services_scraper_competitor.redis_client", fake_redis, raising=False)
    monkeypatch.setattr(scraper_tasks, "redis_client", fake_redis)

@pytest.fixture(scope="session")
def prepare_test_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture()
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture()
def test_user(db_session):
    unique = uuid4().hex
    hashed = hash_password("minha_senha_test")
    user = User(
        id=uuid4(),
        name="Usuario Teste",
        email=f"test_{unique}@example.com",
        phone_number=f"119{unique[:8]}",
        password=hashed,
    )
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture()
def client(db_session, test_user):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user

    with TestClient(app) as c:
        yield c
