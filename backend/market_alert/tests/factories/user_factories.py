from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import factory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserPayloadFactory(factory.DictFactory):
    """ Payload canonico de usuario para testes unitarios e de integracao controlada. """

    id = factory.LazyFunction(uuid4)
    name = factory.Sequence(lambda n: f"Test User {n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    phone_number = factory.Sequence(lambda n: f"+551199999{n:04d}")
    password = "StrongPass123"
    is_active = True
    email_verified = True
    email_verified_at = factory.LazyFunction(_utcnow)
    phone_number_verified = False
    phone_verified_at = None
    status = "active"
    role = "user"
    last_login = None
    created_date = factory.LazyFunction(_utcnow)
    updated_date = factory.LazyFunction(_utcnow)
