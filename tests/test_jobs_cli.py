"""Tests for the failed jobs CLI wrapper."""

import json
from pathlib import Path

import pytest

from cli import jobs_cli
from cli.jobs_cli import (
    export_failed_jobs,
    list_failed_jobs,
    purge_failed_jobs,
    replay_failed_job,
    show_failed_job,
)


class FakeRedis:
    """Fake Redis that supports list ops, delete, and rpush."""

    def __init__(self, values=None):
        self.values = list(values or [])
        self.pushed = []
        self.deleted = []

    def lrange(self, key, start, end):
        return self.values

    def llen(self, key):
        return len(self.values)

    def delete(self, key):
        self.deleted.append(key)
        self.values = []

    def rpush(self, key, value):
        self.pushed.append((key, value))


def _make_record(job_id="abc123", event_type="ip_enrichment", status="failed"):
    return {
        "job_id": job_id,
        "raw_job": json.dumps(
            {
                "job_id": job_id,
                "event_type": event_type,
                "payload": {"ip": "1.1.1.1"},
                "metadata": {"source": "webhook"},
            }
        ),
        "result": {
            "status": status,
            "event_type": event_type,
            "script_path": f"/workspace/musicsheets/{event_type}.py",
            "returncode": 1,
        },
        "failed_at": 1717430400,
    }


@pytest.fixture
def fake_redis(monkeypatch):
    """Provide a fake Redis client to the CLI module."""
    fake = FakeRedis()
    monkeypatch.setattr(jobs_cli, "get_redis_client", lambda: fake)
    monkeypatch.setattr(
        jobs_cli,
        "load_musician_config",
        lambda: {"queue_key": "orchestra:jobs", "dlq_key": "orchestra:dlq"},
    )
    return fake


# list_failed_jobs tests


def test_list_failed_jobs_empty_prints_clear_message(fake_redis, capsys):
    """list_failed_jobs prints '(No failed jobs)' when empty."""
    list_failed_jobs()
    captured = capsys.readouterr()
    assert "No failed jobs" in captured.out


def test_list_failed_jobs_prints_compact_table(fake_redis, capsys):
    """list_failed_jobs prints a compact table for non-empty records."""
    fake_redis.values = [
        json.dumps(_make_record("abc123", "ip_enrichment", "failed")),
        json.dumps(_make_record("def456", "user_lookup", "timeout")),
    ]
    list_failed_jobs()
    captured = capsys.readouterr()
    assert "INDEX" in captured.out
    assert "JOB_ID" in captured.out
    assert "EVENT_TYPE" in captured.out
    assert "abc123" in captured.out
    assert "def456" in captured.out
    assert "ip_enrichment" in captured.out
    assert "user_lookup" in captured.out


def test_list_failed_jobs_skips_malformed_with_warning(fake_redis, capsys):
    """list_failed_jobs skips malformed records and prints a one-line warning."""
    fake_redis.values = [
        json.dumps(_make_record("abc123")),
        "not valid json",
        json.dumps(_make_record("def456")),
    ]
    list_failed_jobs()
    captured = capsys.readouterr()
    assert "abc123" in captured.out
    assert "def456" in captured.out
    assert "malformed" in captured.out
    assert "1 malformed record" in captured.out
    assert "Inspect Redis" in captured.out


# show_failed_job tests


def test_show_failed_job_prints_pretty_json(fake_redis, capsys):
    """show_failed_job prints the matched record as pretty JSON."""
    fake_redis.values = [json.dumps(_make_record("abc123"))]
    show_failed_job("abc123")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["job_id"] == "abc123"


def test_show_failed_job_by_index(fake_redis, capsys):
    """show_failed_job accepts a numeric index."""
    fake_redis.values = [
        json.dumps(_make_record("abc123")),
        json.dumps(_make_record("def456")),
    ]
    show_failed_job("0")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["job_id"] == "abc123"


def test_show_failed_job_missing_ref_exits(fake_redis, capsys):
    """show_failed_job prints error to stderr and exits 1 for missing ref."""
    fake_redis.values = [json.dumps(_make_record("abc123"))]
    with pytest.raises(SystemExit) as exc_info:
        show_failed_job("missing")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No failed job found" in captured.err


# replay_failed_job tests


def test_replay_failed_job_rejects_non_replayable(fake_redis, capsys):
    """replay_failed_job refuses sanitized records with a clear error."""
    fake_redis.values = [json.dumps(_make_record("abc123"))]
    with pytest.raises(SystemExit) as exc_info:
        replay_failed_job("abc123")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "not replayable" in captured.err
    assert fake_redis.pushed == []


def test_replay_failed_job_prints_success_for_replayable(fake_redis, capsys):
    """replay_failed_job enqueues valid replay_jobs and prints success."""
    record = _make_record("abc123")
    record["replay_job"] = {
        "job_id": "abc123",
        "event_type": "ip_enrichment",
        "payload": {"ip": "1.1.1.1"},
        "metadata": {"source": "webhook"},
    }
    fake_redis.values = [json.dumps(record)]
    replay_failed_job("abc123")
    captured = capsys.readouterr()
    assert "Failed job replayed" in captured.out
    assert "abc123" in captured.out
    assert len(fake_redis.pushed) == 1
    key, value = fake_redis.pushed[0]
    assert key == "orchestra:jobs"
    assert json.loads(value)["job_id"] == "abc123"


# purge_failed_jobs tests


def test_purge_failed_jobs_without_yes_refuses(fake_redis, capsys):
    """purge_failed_jobs without --yes refuses and exits 1."""
    fake_redis.values = [json.dumps(_make_record("abc123"))]
    with pytest.raises(SystemExit) as exc_info:
        purge_failed_jobs(yes=False)
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Refusing to purge" in captured.err
    assert fake_redis.deleted == []


def test_purge_failed_jobs_with_yes_deletes(fake_redis, capsys):
    """purge_failed_jobs with --yes deletes all records and reports count."""
    fake_redis.values = [
        json.dumps(_make_record("abc123")),
        json.dumps(_make_record("def456")),
        json.dumps(_make_record("ghi789")),
    ]
    purge_failed_jobs(yes=True)
    captured = capsys.readouterr()
    assert "Purged 3" in captured.out
    assert "orchestra:dlq" in fake_redis.deleted
    assert fake_redis.values == []


# export_failed_jobs tests


def test_export_failed_jobs_without_output_prints_json(fake_redis, capsys):
    """export_failed_jobs without --output prints JSON to stdout."""
    fake_redis.values = [
        json.dumps(_make_record("abc123")),
        json.dumps(_make_record("def456")),
    ]
    export_failed_jobs(output=None)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert len(parsed) == 2
    assert parsed[0]["job_id"] == "abc123"


def test_export_failed_jobs_with_output_writes_file(fake_redis, capsys, tmp_path):
    """export_failed_jobs with --output writes JSON to a file."""
    fake_redis.values = [
        json.dumps(_make_record("abc123")),
        json.dumps(_make_record("def456")),
    ]
    output_path = tmp_path / "failed_jobs.json"
    export_failed_jobs(output=str(output_path))
    captured = capsys.readouterr()
    assert "Exported 2 record(s)" in captured.out
    assert output_path.exists()
    parsed = json.loads(output_path.read_text())
    assert len(parsed) == 2
    assert parsed[0]["job_id"] == "abc123"
