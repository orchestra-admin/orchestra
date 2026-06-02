"""Tests for dedupe module and load_dedupe_config."""

import pytest

from orchestra_core.config import load_dedupe_config
from orchestra_core.dedupe import (
    claim_scheduler_fire,
    claim_webhook_idempotency_key,
    scheduler_dedupe_key,
    webhook_dedupe_key,
)
from orchestra_core.validators import validate_idempotency_key


class FakeRedis:
    """Fake Redis that supports SET NX EX and GET."""

    def __init__(self):
        self.values = {}
        self.ttls = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ex
        return True

    def get(self, key):
        return self.values.get(key)


# validate_idempotency_key tests


def test_validate_idempotency_key_accepts_safe_keys():
    """validate_idempotency_key accepts well-formed keys."""
    safe = [
        "alert-12345",
        "evt_abc",
        "delivery.id.with.dots",
        "gh:12345:abc",
        "a" * 200,
    ]
    for k in safe:
        validate_idempotency_key(k)  # should not raise


def test_validate_idempotency_key_rejects_empty_and_non_string():
    """validate_idempotency_key rejects empty and non-string values."""
    with pytest.raises(ValueError, match="non-empty string"):
        validate_idempotency_key("")
    with pytest.raises(ValueError, match="non-empty string"):
        validate_idempotency_key(None)
    with pytest.raises(ValueError, match="non-empty string"):
        validate_idempotency_key(123)


def test_validate_idempotency_key_rejects_invalid_characters():
    """validate_idempotency_key rejects spaces, slashes, and backslashes."""
    bad = [
        "has space",
        "path/to/file",
        "back\\slash",
        "with/slash",
        "comma,inside",
    ]
    for k in bad:
        with pytest.raises(ValueError, match="alphanumeric"):
            validate_idempotency_key(k)


def test_validate_idempotency_key_rejects_too_long():
    """validate_idempotency_key rejects keys longer than 200 characters."""
    with pytest.raises(ValueError, match="alphanumeric"):
        validate_idempotency_key("a" * 201)


# webhook_dedupe_key tests


def test_webhook_dedupe_key_returns_expected_format():
    """webhook_dedupe_key returns the orchestra-namespaced Redis key."""
    assert webhook_dedupe_key("alert-1") == "orchestra:webhook:idempotency:alert-1"


def test_webhook_dedupe_key_rejects_invalid_input():
    """webhook_dedupe_key rejects invalid keys before building the Redis key."""
    with pytest.raises(ValueError):
        webhook_dedupe_key("has space")
    with pytest.raises(ValueError):
        webhook_dedupe_key("")


# scheduler_dedupe_key tests


def test_scheduler_dedupe_key_returns_expected_format():
    """scheduler_dedupe_key returns the event/minute-namespaced Redis key."""
    assert (
        scheduler_dedupe_key("daily_report", "202606011030")
        == "orchestra:scheduler:fired:daily_report:202606011030"
    )


def test_scheduler_dedupe_key_rejects_invalid_event_type():
    """scheduler_dedupe_key rejects invalid event types via validate_event_type."""
    with pytest.raises(ValueError):
        scheduler_dedupe_key("../escape", "202606011030")


def test_scheduler_dedupe_key_rejects_empty_minute():
    """scheduler_dedupe_key rejects empty minute keys."""
    with pytest.raises(ValueError, match="Minute key"):
        scheduler_dedupe_key("daily_report", "")


# claim_webhook_idempotency_key tests


def test_claim_webhook_idempotency_key_first_claim_succeeds():
    """First claim for a new key returns (True, None)."""
    fake = FakeRedis()
    claimed, existing = claim_webhook_idempotency_key(
        fake, "alert-1", "job-abc", 60
    )
    assert claimed is True
    assert existing is None
    assert fake.values["orchestra:webhook:idempotency:alert-1"] == "job-abc"
    assert fake.ttls["orchestra:webhook:idempotency:alert-1"] == 60


def test_claim_webhook_idempotency_key_duplicate_returns_existing():
    """Duplicate claim returns (False, existing_job_id)."""
    fake = FakeRedis()
    claim_webhook_idempotency_key(fake, "alert-1", "job-abc", 60)
    claimed, existing = claim_webhook_idempotency_key(
        fake, "alert-1", "job-xyz", 60
    )
    assert claimed is False
    assert existing == "job-abc"


def test_claim_webhook_idempotency_key_rejects_invalid_inputs():
    """claim_webhook_idempotency_key validates inputs before touching Redis."""
    fake = FakeRedis()
    with pytest.raises(ValueError):
        claim_webhook_idempotency_key(fake, "", "job-abc", 60)
    with pytest.raises(ValueError):
        claim_webhook_idempotency_key(fake, "alert-1", "", 60)
    with pytest.raises(ValueError):
        claim_webhook_idempotency_key(fake, "alert-1", "job-abc", 0)
    with pytest.raises(ValueError):
        claim_webhook_idempotency_key(fake, "alert-1", "job-abc", -1)


# claim_scheduler_fire tests


def test_claim_scheduler_fire_first_claim_succeeds():
    """First claim for an event/minute returns True."""
    fake = FakeRedis()
    assert claim_scheduler_fire(fake, "daily_report", "202606011030", 120) is True


def test_claim_scheduler_fire_second_claim_fails():
    """Second claim for the same event/minute returns False."""
    fake = FakeRedis()
    assert claim_scheduler_fire(fake, "daily_report", "202606011030", 120) is True
    assert claim_scheduler_fire(fake, "daily_report", "202606011030", 120) is False


def test_claim_scheduler_fire_different_minutes_succeed():
    """Same event type in different minutes produces separate claims."""
    fake = FakeRedis()
    assert claim_scheduler_fire(fake, "daily_report", "202606011030", 120) is True
    assert claim_scheduler_fire(fake, "daily_report", "202606011031", 120) is True


def test_claim_scheduler_fire_different_events_same_minute_succeed():
    """Different event types in the same minute produce separate claims."""
    fake = FakeRedis()
    assert claim_scheduler_fire(fake, "daily_report", "202606011030", 120) is True
    assert claim_scheduler_fire(fake, "weekly_summary", "202606011030", 120) is True


def test_claim_scheduler_fire_rejects_invalid_inputs():
    """claim_scheduler_fire validates inputs before touching Redis."""
    fake = FakeRedis()
    with pytest.raises(ValueError):
        claim_scheduler_fire(fake, "../escape", "202606011030", 120)
    with pytest.raises(ValueError):
        claim_scheduler_fire(fake, "daily_report", "", 120)
    with pytest.raises(ValueError):
        claim_scheduler_fire(fake, "daily_report", "202606011030", 0)


# load_dedupe_config tests


def test_load_dedupe_config_returns_defaults_when_config_missing(
    monkeypatch, tmp_path
):
    """load_dedupe_config returns module defaults when no project config exists."""
    monkeypatch.setattr(
        "orchestra_core.config.get_project_config_path",
        lambda project_root=None: tmp_path / "missing.json",
    )
    cfg = load_dedupe_config()
    assert cfg == {
        "webhook_idempotency_ttl_seconds": 86400,
        "scheduler_ttl_seconds": 120,
    }


def test_load_dedupe_config_returns_defaults_when_dedupe_section_missing(
    monkeypatch, tmp_path
):
    """load_dedupe_config returns defaults when orchestra.json exists but has no dedupe section."""
    cfg_path = tmp_path / "orchestra.json"
    cfg_path.write_text('{"redis": {"host": "localhost"}}')
    monkeypatch.setattr(
        "orchestra_core.config.get_project_config_path",
        lambda project_root=None: cfg_path,
    )
    cfg = load_dedupe_config()
    assert cfg == {
        "webhook_idempotency_ttl_seconds": 86400,
        "scheduler_ttl_seconds": 120,
    }


def test_load_dedupe_config_reads_configured_ttls(monkeypatch, tmp_path):
    """load_dedupe_config reads TTLs from the dedupe section of orchestra.json."""
    cfg_path = tmp_path / "orchestra.json"
    cfg_path.write_text(
        '{"dedupe": {"webhook_idempotency_ttl_seconds": 3600, "scheduler_ttl_seconds": 300}}'
    )
    monkeypatch.setattr(
        "orchestra_core.config.get_project_config_path",
        lambda project_root=None: cfg_path,
    )
    cfg = load_dedupe_config()
    assert cfg == {
        "webhook_idempotency_ttl_seconds": 3600,
        "scheduler_ttl_seconds": 300,
    }
