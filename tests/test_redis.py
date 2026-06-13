"""Tests for the Redis client factory in orchestra_core.redis."""

import pytest


def test_get_redis_client_raises_runtime_error_with_docker_hint(monkeypatch):
    """get_redis_client raises RuntimeError with docker hint on Redis down."""
    from orchestra_core import redis as redis_mod

    def _fake_load_musician_config(project_root=None):
        return {
            "host": "127.0.0.1",
            "port": 1,
            "db": 0,
            "queue_key": "orchestra:jobs",
            "dlq_key": "orchestra:dlq",
        }

    monkeypatch.setattr(redis_mod, "load_musician_config", _fake_load_musician_config)

    with pytest.raises(RuntimeError) as excinfo:
        redis_mod.get_redis_client()

    msg = str(excinfo.value)
    assert "Redis is not reachable at 127.0.0.1:1" in msg
    assert "docker compose up -d redis" in msg
