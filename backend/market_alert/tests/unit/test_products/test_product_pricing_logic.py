""" Testes unitarios para helpers de service do lifecycle de produtos. """

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from market_alert.products.crud.crud_monitored import (
    MonitoredLockError,
    MonitoredNotFoundError,
    MonitoredOwnershipError,
)
from market_alert.products.services import services_competitor_lifecycle, services_monitored_lifecycle


pytestmark = pytest.mark.unit


def test_raise_from_monitored_error_maps_not_found() -> None:
    with pytest.raises(HTTPException) as exc_info:
        services_monitored_lifecycle._raise_from_monitored_error(
            MonitoredNotFoundError("missing")
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


def test_raise_from_monitored_error_maps_ownership_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        services_monitored_lifecycle._raise_from_monitored_error(
            MonitoredOwnershipError("forbidden")
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_raise_from_monitored_error_maps_lock_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        services_monitored_lifecycle._raise_from_monitored_error(
            MonitoredLockError("locked")
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_validate_competitor_limit_raises_when_limit_is_reached(monkeypatch) -> None:
    monkeypatch.setattr(
        services_competitor_lifecycle,
        "count_competitors_by_monitored",
        lambda db, monitored_product_id, include_paused=True: 3,
    )

    with pytest.raises(HTTPException) as exc_info:
        services_competitor_lifecycle._validate_competitor_limit(
            db=object(),
            monitored_product_id=uuid4(),
            limit=3,
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_enforce_competitor_scrape_rate_limit_skips_when_config_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        services_competitor_lifecycle,
        "parse_rate_limit_config",
        lambda raw_value: None,
    )
    monkeypatch.setattr(
        services_competitor_lifecycle,
        "allow_with_leaky_bucket",
        lambda bucket_key, rate_limit: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    services_competitor_lifecycle._enforce_competitor_scrape_rate_limit(uuid4())


def test_enforce_competitor_scrape_rate_limit_raises_when_bucket_denies(monkeypatch) -> None:
    monkeypatch.setattr(
        services_competitor_lifecycle,
        "parse_rate_limit_config",
        lambda raw_value: (10, 60),
    )
    monkeypatch.setattr(
        services_competitor_lifecycle,
        "allow_with_leaky_bucket",
        lambda bucket_key, rate_limit: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        services_competitor_lifecycle._enforce_competitor_scrape_rate_limit(uuid4())

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
