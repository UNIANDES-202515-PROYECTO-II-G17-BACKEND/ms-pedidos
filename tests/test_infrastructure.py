from unittest.mock import patch
from src.infrastructure.infrastructure import get_redis

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
