"""Fixtures compartilhadas para testes do ciclo de vida de produtos.

Este módulo fornece sessão SQLite em memória e fábricas mínimas para
instanciar usuário, monitorado e concorrente sem depender de infraestrutura
externa.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from market_alert.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from market_alert.enums.enums_users import UserStatus
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.models.models_users import User


@pytest.fixture()
def db_session() -> Session:
    """Cria sessão transacional com SQLite em memória para cada teste."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    MonitoredProduct.__table__.create(engine)
    CompetitorProduct.__table__.create(engine)

    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db_session: Session) -> User:
    """Persiste usuário padrão para os cenários de serviço e integração."""
    model = User(
        id=uuid.uuid4(),
        name="Usuário Teste",
        email=f"teste-{uuid.uuid4()}@example.com",
        password=b"hashed",
        phone_number=str(uuid.uuid4())[:20],
        status=UserStatus.active,
        is_active=True,
        email_verified=True,
    )
    db_session.add(model)
    db_session.commit()
    db_session.refresh(model)
    return model


@pytest.fixture()
def monitored(db_session: Session, user: User) -> MonitoredProduct:
    """Persiste um monitorado ativo para cobrir cenários de atualização."""
    model = MonitoredProduct(
        id=uuid.uuid4(),
        user_id=user.id,
        name_identification="Produto Base",
        monitoring_type=MonitoringType.scraping,
        product_url="https://example.com/p/base",
        normalized_url="https://example.com/p/base",
        status=MonitoredStatus.active,
        current_price=Decimal("100.00"),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(model)
    db_session.commit()
    db_session.refresh(model)
    return model


@pytest.fixture()
def competitor(db_session: Session, monitored: MonitoredProduct) -> CompetitorProduct:
    """Persiste concorrente vinculado ao monitorado de teste."""
    model = CompetitorProduct(
        id=uuid.uuid4(),
        monitored_product_id=monitored.id,
        name_competitor="Concorrente Base",
        product_url="https://concorrente.com/p/base",
        status=ProductStatus.available,
    )
    db_session.add(model)
    db_session.commit()
    db_session.refresh(model)
    return model
