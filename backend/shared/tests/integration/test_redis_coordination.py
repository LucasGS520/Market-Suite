from __future__ import annotations

import json
import time

import pytest


pytestmark = pytest.mark.integration


class FakeStreamRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, object]]]] = {}
        self.groups: dict[tuple[str, str], dict[str, object]] = {}

    @staticmethod
    def _index(event_id: str) -> int:
        return int(event_id.split("-", 1)[0])

    def xadd(self, key: str, fields: dict[str, object], maxlen: int = 10_000, approximate: bool = True):
        stream = self.streams.setdefault(key, [])
        event_id = f"{len(stream) + 1}-0"
        stream.append((event_id, dict(fields)))
        return event_id

    def xlen(self, key: str) -> int:
        return len(self.streams.get(key, []))

    def xrange(self, key: str, count: int = 100):
        return list(self.streams.get(key, []))[:count]

    def xread(self, streams: dict[str, str], count: int = 100, block: int | None = None):
        key, last_id = next(iter(streams.items()))
        items = [
            item for item in self.streams.get(key, [])
            if self._index(item[0]) > self._index(last_id)
        ][:count]
        return [(key, items)] if items else []

    def xgroup_create(self, name: str, groupname: str, id: str = "0-0", mkstream: bool = True):
        group_key = (name, groupname)
        if group_key in self.groups:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        if mkstream:
            self.streams.setdefault(name, [])
        self.groups[group_key] = {"last_id": id, "pending": set()}
        return True

    def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int = 100,
        block: int | None = None,
    ):
        key, last_id = next(iter(streams.items()))
        state = self.groups[(key, groupname)]
        checkpoint = state["last_id"] if last_id == ">" else last_id
        items = [
            item for item in self.streams.get(key, [])
            if self._index(item[0]) > self._index(checkpoint)
        ][:count]
        if items:
            state["last_id"] = items[-1][0]
            state["pending"].update(item[0] for item in items)
            return [(key, items)]
        return []

    def xack(self, key: str, group: str, event_id: str) -> int:
        state = self.groups[(key, group)]
        if event_id in state["pending"]:
            state["pending"].remove(event_id)
            return 1
        return 0


class BrokenStreamRedis:
    def xadd(self, *args, **kwargs):
        raise RuntimeError("boom")

    def xlen(self, *args, **kwargs):
        raise RuntimeError("boom")

    def xrange(self, *args, **kwargs):
        raise RuntimeError("boom")

    def xread(self, *args, **kwargs):
        raise RuntimeError("boom")

    def xgroup_create(self, *args, **kwargs):
        raise RuntimeError("boom")

    def xreadgroup(self, *args, **kwargs):
        raise RuntimeError("boom")

    def xack(self, *args, **kwargs):
        raise RuntimeError("boom")


class FakePublishRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, message: str) -> None:
        if self.fail:
            raise RuntimeError("publish failed")
        self.published.append((channel, message))


class FakeLoop:
    def is_closed(self) -> bool:
        return False

    def call_soon_threadsafe(self, callback, *args):
        callback(*args)


class FakePubSub:
    def __init__(self, messages: list[dict[str, object]], stop_event) -> None:
        self.messages = messages
        self.stop_event = stop_event
        self.subscriptions: list[str] = []

    def subscribe(self, channel: str) -> None:
        self.subscriptions.append(channel)

    def listen(self):
        yield {"type": "subscribe", "data": 1}
        for message in self.messages:
            yield message
        while not self.stop_event.is_set():
            time.sleep(0.01)


class FakeSubscriberRedis:
    def __init__(self, messages: list[dict[str, object]], stop_event) -> None:
        self.messages = messages
        self.stop_event = stop_event

    def pubsub(self):
        return FakePubSub(self.messages, self.stop_event)


class BrokenSubscriberRedis:
    def pubsub(self):
        return self

    def subscribe(self, channel: str) -> None:
        return None

    def listen(self):
        raise RuntimeError("listener down")


def test_stream_helpers_cover_publish_read_group_and_ack(monkeypatch):
    import shared.infra.redis.streams as module

    redis = FakeStreamRedis()
    monkeypatch.setattr("shared.utils.redis_client.get_redis_operational", lambda: redis)

    event_id = module.xadd_event("stream:test", {"kind": "created"})
    assert event_id == "1-0"
    assert module.xlen_stream("stream:test") == 1
    assert module.xrange_stream("stream:test") == [("1-0", {"kind": "created"})]
    assert module.xread_stream("stream:test", last_id="0-0") == [("1-0", {"kind": "created"})]
    assert module.ensure_consumer_group("stream:test", group="workers")
    assert module.ensure_consumer_group("stream:test", group="workers")
    assert module.xreadgroup_stream("stream:test", group="workers", consumer="c1") == [
        ("1-0", {"kind": "created"})
    ]
    assert module.xack_stream("stream:test", group="workers", event_id="1-0") == 1


def test_stream_helpers_degrade_safely_on_errors(monkeypatch):
    import shared.infra.redis.streams as module

    monkeypatch.setattr("shared.utils.redis_client.get_redis_operational", lambda: BrokenStreamRedis())

    assert module.xadd_event("stream:test", {"kind": "created"}) is None
    assert module.xlen_stream("stream:test") == -1
    assert module.xrange_stream("stream:test") == []
    assert module.xread_stream("stream:test") == []
    assert module.ensure_consumer_group("stream:test", group="workers") is False
    assert module.xreadgroup_stream("stream:test", group="workers", consumer="c1") == []
    assert module.xack_stream("stream:test", group="workers", event_id="1-0") == 0


def test_publish_message_serializes_payload_and_handles_failures(monkeypatch):
    import shared.infra.redis_pubsub as module

    ok_client = FakePublishRedis()
    monkeypatch.setattr(module, "get_redis_operational", lambda: ok_client)

    assert module.publish_message("updates", {"id": 1, "status": "ok"}) is True
    assert ok_client.published == [("updates", json.dumps({"id": 1, "status": "ok"}))]

    monkeypatch.setattr(module, "get_redis_operational", lambda: None)
    assert module.publish_message("updates", {"id": 2}) is False

    monkeypatch.setattr(module, "get_redis_operational", lambda: FakePublishRedis(fail=True))
    assert module.publish_message("updates", {"id": 3}) is False


def test_subscriber_delivers_valid_payload_and_recovers_after_listener_error(monkeypatch):
    import shared.infra.redis_pubsub as module

    stop_ref: dict[str, object] = {}
    calls = {"count": 0}
    sleeps: list[float] = []
    real_sleep = time.sleep

    def _from_url(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return BrokenSubscriberRedis()
        return FakeSubscriberRedis(
            [
                {"type": "message", "data": "not-json"},
                {"type": "message", "data": json.dumps({"event": "ready"})},
            ],
            stop_ref["event"],
        )

    monkeypatch.setattr(module.redis.Redis, "from_url", _from_url)
    monkeypatch.setattr(
        module.time,
        "sleep",
        lambda seconds: sleeps.append(seconds) or real_sleep(0.001),
    )

    subscriber = module.RedisChannelSubscriber("updates", reconnect_interval=0.01)
    stop_ref["event"] = subscriber._stop_event
    subscriber.start(loop=FakeLoop())

    deadline = time.time() + 1.0
    while subscriber.queue.empty() and time.time() < deadline:
        time.sleep(0.01)

    payload = subscriber.queue.get_nowait()
    subscriber.stop()

    assert payload == {"event": "ready"}
    assert sleeps
    assert sleeps[0] == 0.01
