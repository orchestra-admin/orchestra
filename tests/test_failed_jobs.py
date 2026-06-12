"""Tests for failed jobs service helpers."""

import json

from conductor.conductor_tasks.failed_jobs import (
    export_failed_jobs,
    find_failed_job,
    is_replayable_failed_job,
    list_failed_jobs,
    purge_failed_jobs,
    replay_failed_job,
)


class FakeRedis:
    """Fake Redis that supports list ops and delete."""

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


# list_failed_jobs tests


def test_list_failed_jobs_parses_json_records():
    """list_failed_jobs parses JSON records from Redis."""
    fake = FakeRedis(
        values=[
            json.dumps(_make_record("abc123")),
            json.dumps(_make_record("def456", "user_lookup", "timeout")),
        ]
    )
    records = list_failed_jobs(fake, "orchestra:dlq")
    assert len(records) == 2
    assert records[0]["job_id"] == "abc123"
    assert records[1]["job_id"] == "def456"


def test_list_failed_jobs_decodes_bytes_records():
    """list_failed_jobs handles bytes records (real Redis returns bytes)."""
    fake = FakeRedis(values=[json.dumps(_make_record()).encode("utf-8")])
    records = list_failed_jobs(fake, "orchestra:dlq")
    assert len(records) == 1
    assert records[0]["job_id"] == "abc123"


def test_list_failed_jobs_handles_malformed_json():
    """list_failed_jobs tags malformed records with a malformed flag."""
    fake = FakeRedis(
        values=[
            json.dumps(_make_record("abc123")),
            "not valid json",
            "12345",  # valid JSON but not a dict
            json.dumps(_make_record("def456")),
        ]
    )
    records = list_failed_jobs(fake, "orchestra:dlq")
    assert len(records) == 4
    assert records[0]["job_id"] == "abc123"
    assert records[1] == {"malformed": True, "raw": "not valid json"}
    assert records[2] == {"malformed": True, "raw": "12345"}
    assert records[3]["job_id"] == "def456"


# find_failed_job tests


def test_find_failed_job_by_numeric_index():
    """find_failed_job finds a record by zero-based numeric index."""
    records = [
        _make_record("abc123"),
        _make_record("def456"),
        _make_record("ghi789"),
    ]
    result = find_failed_job(records, "1")
    assert result == (1, records[1])


def test_find_failed_job_by_top_level_job_id():
    """find_failed_job finds a record by top-level job_id."""
    records = [
        _make_record("abc123"),
        _make_record("def456"),
    ]
    result = find_failed_job(records, "def456")
    assert result == (1, records[1])


def test_find_failed_job_by_nested_raw_job_job_id():
    """find_failed_job finds a record by job_id inside the raw_job JSON string."""
    records = [
        {"job_id": None, "raw_job": json.dumps({"job_id": "nested-1"})},
        _make_record("abc123"),
    ]
    result = find_failed_job(records, "nested-1")
    assert result == (0, records[0])


def test_find_failed_job_returns_none_for_missing_ref():
    """find_failed_job returns None when the ref doesn't match any record."""
    records = [_make_record("abc123")]
    assert find_failed_job(records, "missing") is None
    assert find_failed_job(records, "99") is None  # out of range


def test_find_failed_job_skips_malformed_records():
    """find_failed_job by job_id skips records tagged as malformed."""
    records = [
        {"malformed": True, "raw": "abc123"},
        _make_record("abc123"),
    ]
    result = find_failed_job(records, "abc123")
    assert result == (1, records[1])


# export_failed_jobs tests


def test_export_failed_jobs_returns_valid_pretty_json():
    """export_failed_jobs returns a valid pretty JSON string."""
    records = [
        _make_record("abc123", "ip_enrichment"),
        _make_record("def456", "user_lookup"),
    ]
    output = export_failed_jobs(records)
    assert output.endswith("\n")
    parsed = json.loads(output)
    assert len(parsed) == 2
    assert parsed[0]["job_id"] == "abc123"


# purge_failed_jobs tests


def test_purge_failed_jobs_deletes_key_and_returns_count():
    """purge_failed_jobs deletes the configured key and returns the deleted count."""
    fake = FakeRedis(
        values=[
            json.dumps(_make_record("abc123")),
            json.dumps(_make_record("def456")),
            json.dumps(_make_record("ghi789")),
        ]
    )
    count = purge_failed_jobs(fake, "orchestra:dlq")
    assert count == 3
    assert "orchestra:dlq" in fake.deleted
    assert fake.values == []


def test_purge_failed_jobs_returns_zero_for_empty_queue():
    """purge_failed_jobs returns 0 when there are no records."""
    fake = FakeRedis()
    count = purge_failed_jobs(fake, "orchestra:dlq")
    assert count == 0
    assert "orchestra:dlq" in fake.deleted


# is_replayable_failed_job tests


def test_is_replayable_false_for_sanitized_record():
    """is_replayable_failed_job returns False for records without replay_job."""
    record = _make_record("abc123")
    assert is_replayable_failed_job(record) is False


def test_is_replayable_true_for_valid_replay_job():
    """is_replayable_failed_job returns True when replay_job is a valid queue job."""
    record = _make_record("abc123")
    record["replay_job"] = {
        "job_id": "abc123",
        "event_type": "ip_enrichment",
        "payload": {"ip": "1.1.1.1"},
        "metadata": {"source": "webhook"},
    }
    assert is_replayable_failed_job(record) is True


def test_is_replayable_false_for_malformed_replay_job():
    """Returns False when replay_job fails parse_job validation."""
    record = _make_record("abc123")
    record["replay_job"] = {"event_type": ""}  # missing event_type
    assert is_replayable_failed_job(record) is False


def test_is_replayable_false_when_replay_job_not_dict():
    """is_replayable_failed_job returns False when replay_job is not a dict."""
    record = _make_record("abc123")
    record["replay_job"] = "not a dict"
    assert is_replayable_failed_job(record) is False


# replay_failed_job tests


def test_replay_failed_job_rejects_non_replayable_record():
    """replay_failed_job rejects sanitized records with a clear error."""
    fake = FakeRedis()
    record = _make_record("abc123")  # no replay_job
    replayed, job_id, error = replay_failed_job(fake, "orchestra:jobs", record)
    assert replayed is False
    assert job_id is None
    assert "not replayable" in error
    assert fake.pushed == []


def test_replay_failed_job_enqueues_valid_replay_job():
    """replay_failed_job pushes a valid replay_job to the normal queue."""
    fake = FakeRedis()
    record = _make_record("abc123")
    record["replay_job"] = {
        "job_id": "abc123",
        "event_type": "ip_enrichment",
        "payload": {"ip": "1.1.1.1"},
        "metadata": {"source": "webhook"},
    }
    replayed, job_id, error = replay_failed_job(fake, "orchestra:jobs", record)
    assert replayed is True
    assert job_id == "abc123"
    assert error is None
    assert len(fake.pushed) == 1
    key, value = fake.pushed[0]
    assert key == "orchestra:jobs"
    assert json.loads(value)["job_id"] == "abc123"


def test_replay_failed_job_rejects_invalid_replay_job():
    """replay_failed_job rejects records whose replay_job fails validation."""
    fake = FakeRedis()
    record = _make_record("abc123")
    record["replay_job"] = {"event_type": ""}  # missing required fields
    replayed, job_id, error = replay_failed_job(fake, "orchestra:jobs", record)
    assert replayed is False
    assert job_id is None
    assert "not replayable" in error
    assert fake.pushed == []
