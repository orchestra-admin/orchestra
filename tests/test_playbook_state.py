from pathlib import Path

import pytest

from orchestra_core.playbook_state import (
    activate_playbook_state,
    deactivate_playbook_state,
    load_deactivated_playbooks,
    save_deactivated_playbooks,
    sync_deactivated_playbooks,
)


def _write_config(project_root: Path, data: dict) -> None:
    config_dir = project_root / ".local_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_dir / "orchestra.json", "w") as f:
        import json
        json.dump(data, f)


def test_load_deactivated_missing_config(tmp_path: Path) -> None:
    """load_deactivated_playbooks returns an empty set when config is missing."""
    assert load_deactivated_playbooks(tmp_path) == set()


def test_load_deactivated_missing_section(tmp_path: Path) -> None:
    """load_deactivated_playbooks returns an empty set when the section is absent."""
    _write_config(tmp_path, {"redis": {"host": "x"}})
    assert load_deactivated_playbooks(tmp_path) == set()


def test_load_deactivated_existing_section(tmp_path: Path) -> None:
    """load_deactivated_playbooks returns a set of deactivated event types."""
    _write_config(
        tmp_path,
        {"playbooks": {"deactivated": ["ip_enrichment", "suspicious_login"]}},
    )
    assert load_deactivated_playbooks(tmp_path) == {
        "ip_enrichment",
        "suspicious_login",
    }


def test_save_deactivated_writes_sorted(tmp_path: Path) -> None:
    """save_deactivated_playbooks persists event types as a sorted list."""
    save_deactivated_playbooks(tmp_path, {"zebra", "alpha", "mike"})

    config_path = tmp_path / ".local_config" / "orchestra.json"
    import json
    with open(config_path) as f:
        data = json.load(f)
    assert data["playbooks"]["deactivated"] == ["alpha", "mike", "zebra"]


def test_save_deactivated_preserves_unrelated_sections(tmp_path: Path) -> None:
    """save_deactivated_playbooks leaves non-playbook config sections intact."""
    _write_config(
        tmp_path,
        {"redis": {"host": "1.2.3.4", "port": 6379}, "llm": {"provider": "openai"}},
    )

    save_deactivated_playbooks(tmp_path, {"foo"})

    import json
    with open(tmp_path / ".local_config" / "orchestra.json") as f:
        data = json.load(f)
    assert data["redis"] == {"host": "1.2.3.4", "port": 6379}
    assert data["llm"] == {"provider": "openai"}
    assert data["playbooks"]["deactivated"] == ["foo"]


def test_deactivate_playbook_state_adds_event_type(tmp_path: Path) -> None:
    """deactivate_playbook_state adds the event type to config and returns True."""
    assert deactivate_playbook_state(tmp_path, "ip_enrichment") is True
    assert load_deactivated_playbooks(tmp_path) == {"ip_enrichment"}


def test_deactivate_playbook_state_duplicate_is_idempotent(tmp_path: Path) -> None:
    """deactivate returns False when the playbook is already deactivated."""
    deactivate_playbook_state(tmp_path, "ip_enrichment")
    assert deactivate_playbook_state(tmp_path, "ip_enrichment") is False
    assert load_deactivated_playbooks(tmp_path) == {"ip_enrichment"}


def test_activate_playbook_state_removes_event_type(tmp_path: Path) -> None:
    """activate_playbook_state removes the event type from config and returns True."""
    deactivate_playbook_state(tmp_path, "ip_enrichment")
    assert activate_playbook_state(tmp_path, "ip_enrichment") is True
    assert load_deactivated_playbooks(tmp_path) == set()


def test_activate_playbook_state_duplicate_is_idempotent(tmp_path: Path) -> None:
    """activate_playbook_state returns False when the playbook is already active."""
    assert activate_playbook_state(tmp_path, "ip_enrichment") is False
    assert load_deactivated_playbooks(tmp_path) == set()


def test_playbook_state_rejects_invalid_event_type(tmp_path: Path) -> None:
    """Invalid event types are rejected by deactivate and activate helpers."""
    with pytest.raises(ValueError):
        deactivate_playbook_state(tmp_path, "bad/event")
    with pytest.raises(ValueError):
        activate_playbook_state(tmp_path, "bad event")
    assert load_deactivated_playbooks(tmp_path) == set()


class _FakeRedis:
    def __init__(self) -> None:
        self.store: set[str] = set()

    def delete(self, key: str) -> int:
        existed = bool(self.store)
        self.store.clear()
        return 1 if existed else 0

    def sadd(self, key: str, *members: str) -> int:
        added = 0
        for m in members:
            if m not in self.store:
                self.store.add(m)
                added += 1
        return added


def test_sync_replaces_stale_redis_with_durable_config(tmp_path: Path) -> None:
    """sync deletes stale Redis state and repopulates only from config."""
    redis_client = _FakeRedis()
    redis_client.store.add("stale_only")
    redis_client.store.add("ip_enrichment")

    _write_config(
        tmp_path,
        {"playbooks": {"deactivated": ["ip_enrichment", "suspicious_login"]}},
    )

    synced = sync_deactivated_playbooks(redis_client, tmp_path)

    assert synced == {"ip_enrichment", "suspicious_login"}
    assert redis_client.store == {"ip_enrichment", "suspicious_login"}
