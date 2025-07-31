""" Fixtures e utilidades para testes de integração """

import os
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import uuid4

from infra.db import Base
from infra.db import get_db

from main import app
from app.core.security import get_current_user
from app.core.password import hash_password
from app.models.models_users import User

from app.utils import rate_limiter as rate_limiter_module
from app.tasks import scraper_tasks

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
def patch_rate_limiter_and_redis(monkeypatch):
    """ Mocka Redis, RateLimiter e CircuitBreaker antes de qualquer uso em integração """

    class FakeRedis:
        def get(self, *args, **kwargs): return None
        def set(self, *args, **kwargs): pass
        def exists(self, *args, **kwargs): return False
        def script_load(self, *args, **kwargs): return "mock_sha"
        def evalsha(self, *args, **kwargs): return 1

    class MockRateLimiter:
        def __init__(self, *args, **kwargs): pass
        def allow_request(self, *args, **kwargs): return True
        def reset(self, *args, **kwargs): pass
        def get_count(self, *args, **kwargs): return 0

    class MockCircuitBreaker:
        def allow_request(self, *args, **kwargs): return True
        def record_success(self, *args, **kwargs): pass
        def record_failure(self, *args, **kwargs): pass

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

    monkeypatch.setattr("app.utils.redis_client.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("app.utils.redis_client._redis_client", fake_redis)
    #Usa raising False pois esses atributos podem não existir nos módulos
    monkeypatch.setattr("app.services.services_scraper_monitored.redis_client", fake_redis, raising=False)
    monkeypatch.setattr("app.services.services_scraper_competitor.redis_client", fake_redis, raising=False)
    monkeypatch.setattr("app.services.services_scraper_common.redis_client", fake_redis)
    monkeypatch.setattr(scraper_tasks, "redis_client", fake_redis)
    monkeypatch.setattr("app.services.services_cache_scraper.cache_manager", cache)

    #Substitui o RateLimiter em todos os módulos
    monkeypatch.setattr(rate_limiter_module, "RateLimiter", MockRateLimiter)
    monkeypatch.setattr("app.services.services_scraper_monitored.RateLimiter", MockRateLimiter)
    monkeypatch.setattr("app.services.services_scraper_competitor.RateLimiter", MockRateLimiter)
    monkeypatch.setattr("app.services.services_scraper_common.RateLimiter", MockRateLimiter)
    monkeypatch.setattr(scraper_tasks, "RateLimiter", MockRateLimiter)

    #Substitui CircuitBreaker nos serviços e tasks
    monkeypatch.setattr("app.services.services_scraper_monitored.CircuitBreaker", lambda: MockCircuitBreaker())
    monkeypatch.setattr("app.services.services_scraper_competitor.CircuitBreaker", lambda: MockCircuitBreaker())
    monkeypatch.setattr("app.services.services_scraper_common.CircuitBreaker", lambda: MockCircuitBreaker())
    monkeypatch.setattr(scraper_tasks, "circuit_breaker", MockCircuitBreaker())

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
