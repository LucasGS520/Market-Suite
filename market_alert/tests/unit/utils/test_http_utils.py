import pytest
from datetime import datetime, timezone, timedelta

from app.utils.http_utils import parse_retry_after

def test_parse_retry_after_seconds():
    assert parse_retry_after("30") == 30

def test_parse_retry_after_http_date():
    future = datetime.now(timezone.utc) + timedelta(seconds=20)
    header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    result = parse_retry_after(header)
    assert 0 < result <= 20
