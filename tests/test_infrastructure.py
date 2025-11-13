from unittest.mock import patch

import pytest

from src.infrastructure.infrastructure import get_redis
from src.infrastructure.infrastructure import publish_event
import json
from unittest.mock import MagicMock
from uuid import uuid4

def test_get_redis_none_when_not_configured(monkeypatch):
    # Patch settings inside module
    import src.infrastructure.infrastructure as infra
    monkeypatch.setattr(infra.settings, "REDIS_HOST", "")
    monkeypatch.setattr(infra.settings, "REDIS_PORT", "")
    assert get_redis() is None

def test_get_redis_returns_client(monkeypatch):
    import src.infrastructure.infrastructure as infra
    monkeypatch.setattr(infra.settings, "REDIS_HOST", "localhost")
    monkeypatch.setattr(infra.settings, "REDIS_PORT", "6379")
    class DummyRedis:
        def __init__(self, *a, **k): pass
    monkeypatch.setattr(infra, "Redis", DummyRedis)
    # reset singleton
    monkeypatch.setattr(infra, "_redis_client", None, raising=False)
    assert get_redis() is not None


def test_publish_event_ok(monkeypatch):
    import src.infrastructure.infrastructure as infra

    class DummyFuture:
        def __init__(self):
            self.called = False
        def result(self, timeout=None):
            self.called = True

    class DummyPublisher:
        def __init__(self):
            self.calls = []
        def publish(self, topic, payload):
            self.calls.append((topic, payload))
            return DummyFuture()

    dummy = DummyPublisher()

    # 👇 Ahora mockeamos get_publisher, NO el publisher global
    monkeypatch.setattr(infra, "get_publisher", lambda: dummy)

    topic = f"projects/test/topics/{uuid4()}"
    data = {"foo": "bar", "n": 1}

    publish_event(data, topic)

    assert len(dummy.calls) == 1
    sent_topic, sent_payload = dummy.calls[0]
    assert sent_topic == topic
    decoded = json.loads(sent_payload.decode("utf-8"))
    assert decoded == data


def test_publish_event_propagates_error(monkeypatch):
    import src.infrastructure.infrastructure as infra

    class BoomPublisher:
        def publish(self, topic, payload):
            raise RuntimeError("pubsub error")

    monkeypatch.setattr(infra, "get_publisher", lambda: BoomPublisher())

    with pytest.raises(RuntimeError):
        publish_event({"x": 1}, "projects/test/topics/x")