from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import factory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MonitoredProductPayloadFactory(factory.DictFactory):
    """ Contrato base de produto monitorado usado em testes de dominio. """

    id = factory.LazyFunction(uuid4)
    owner_id = factory.LazyFunction(uuid4)
    display_name = factory.Sequence(lambda n: f"Monitorado {n}")
    name = factory.LazyAttribute(lambda obj: obj.display_name)
    url = factory.Sequence(lambda n: f"https://store.example.com/products/{n}")
    normalized_url = factory.LazyAttribute(lambda obj: obj.url)
    current_price = Decimal("199.90")
    currency = "BRL"
    source = "monitored"
    availability = True
    last_status = "collected"
    display_status = "competitive"
    thumbnail = "https://cdn.example.com/images/monitorado.png"
    created_at = factory.LazyFunction(_utcnow)
    last_scraped_at = factory.LazyFunction(_utcnow)
    last_collected_at = factory.LazyFunction(_utcnow)
    next_check_at = factory.LazyFunction(_utcnow)
    last_price_change_at = factory.LazyFunction(_utcnow)
    stability = "stable"
    monitored_since = factory.LazyAttribute(lambda obj: obj.created_at)
    last_price_change_global_at = factory.LazyFunction(_utcnow)
    competitiveness_status = "competitive"
    is_featured = False
    paused = False
    paused_at = None
    comparison_summary = None


class CompetitorProductPayloadFactory(factory.DictFactory):
    """ Contrato base de concorrente vinculado a um monitorado. """

    id = factory.LazyFunction(uuid4)
    monitored_product_id = factory.LazyFunction(uuid4)
    display_name = factory.Sequence(lambda n: f"Concorrente {n}")
    name = factory.LazyAttribute(lambda obj: obj.display_name)
    url = factory.Sequence(lambda n: f"https://competitor.example.com/products/{n}")
    current_price = Decimal("189.90")
    currency = "BRL"
    source = "competitor"
    availability = True
    last_status = "collected"
    last_checked = factory.LazyFunction(_utcnow)
    last_scraped_at = factory.LazyFunction(_utcnow)
    is_paused = False
    thumbnail = "https://cdn.example.com/images/concorrente.png"
