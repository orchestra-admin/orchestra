import json
import sys
from pathlib import Path

import pytest

from conductor.conductor_tasks.musician import (
    build_queue_job,
    execute_job,
    parse_job,
    push_dlq_record,
    resolve_script_path,
)


class FakeRedis:
    """Fake Redis client for testing DLQ operations."""

    def __init__(self):
        self.items = []

    def rpush(self, key, value):
        self.items.append((key, value))


# parse_job tests


def test_parse_job_rejects_invalid_json():
    """parse_job raises ValueError for invalid JSON."""
    with pytest.raises(ValueError, match="Job must be valid JSON"):
        parse_job("not valid json")


def test_parse_job_rejects_json_arrays():
    """parse_job raises ValueError for JSON arrays."""
    with pytest.raises(ValueError, match="Job must be a JSON object"):
        parse_job('["array", "not", "object"]')


def test_parse_job_rejects_json_strings():
    """parse_job raises ValueError for JSON strings."""
    with pytest.raises(ValueError, match="Job must be a JSON object"):
        parse_job('"just a string"')


def test_parse_job_rejects_missing_event_type():
    """parse_job raises ValueError when event_type is missing."""
    with pytest.raises(ValueError, match="Job must include a non-empty string field 'event_type'"):
        parse_job(json.dumps({"payload": {}}))


def test_parse_job_rejects_non_string_event_type():
    """parse_job raises ValueError when event_type is not a string."""
    with pytest.raises(ValueError, match="Job must include a non-empty string field 'event_type'"):
        parse_job(json.dumps({"event_type": 123, "payload": {}}))


def test_parse_job_rejects_empty_event_type():
    """parse_job raises ValueError when event_type is empty."""
    with pytest.raises(ValueError, match="Job must include a non-empty string field 'event_type'"):
        parse_job(json.dumps({"event_type": "", "payload": {}}))


def test_parse_job_rejects_non_dict_payload():
    """parse_job raises ValueError when payload is not a dict."""
    with pytest.raises(ValueError, match="Job must include an object field 'payload'"):
        parse_job(json.dumps({"event_type": "test", "payload": "not a dict"}))


def test_parse_job_accepts_valid_job():
    """parse_job accepts valid jobs and preserves fields."""
    raw = json.dumps({
        "event_type": "ip_enrichment",
        "payload": {"ip": "1.1.1.1"},
        "metadata": {"source": "webhook"},
    })
    result = parse_job(raw)
    assert result["event_type"] == "ip_enrichment"
    assert result["payload"] == {"ip": "1.1.1.1"}
    assert result["metadata"] == {"source": "webhook"}


def test_parse_job_defaults_metadata_to_empty_dict():
    """parse_job defaults metadata to empty dict when not provided."""
    raw = json.dumps({"event_type": "test", "payload": {}})
    result = parse_job(raw)
    assert result["metadata"] == {}


# build_queue_job tests


def test_build_queue_job_adds_metadata():
    """build_queue_job adds job_id, source, and received_at."""
    job = build_queue_job({"event_type": "test", "data": "value"})
    assert "job_id" in job
    assert len(job["job_id"]) == 32  # UUID hex
    assert job["event_type"] == "test"
    assert job["payload"] == {"event_type": "test", "data": "value"}
    assert job["metadata"]["source"] == "webhook"
    assert "received_at" in job["metadata"]


def test_build_queue_job_accepts_custom_source():
    """build_queue_job accepts custom source parameter."""
    job = build_queue_job({"event_type": "test"}, source="schedule")
    assert job["metadata"]["source"] == "schedule"


def test_build_queue_job_merges_custom_metadata():
    """build_queue_job merges custom metadata with default metadata."""
    job = build_queue_job(
        {"event_type": "test"},
        metadata={"client": "192.168.1.1"},
    )
    assert job["metadata"]["source"] == "webhook"
    assert job["metadata"]["client"] == "192.168.1.1"
    assert "received_at" in job["metadata"]


def test_build_queue_job_rejects_empty_event_type():
    """build_queue_job raises ValueError for empty event_type."""
    with pytest.raises(ValueError, match="Payload must include a non-empty string field 'event_type'"):
        build_queue_job({"event_type": ""})


def test_build_queue_job_rejects_missing_event_type():
    """build_queue_job raises ValueError when event_type is missing."""
    with pytest.raises(ValueError, match="Payload must include a non-empty string field 'event_type'"):
        build_queue_job({"data": "no event_type"})


def test_build_queue_job_rejects_slashes():
    """build_queue_job rejects event_type with forward slashes."""
    with pytest.raises(ValueError, match="contains invalid characters"):
        build_queue_job({"event_type": "path/to/file"})


def test_build_queue_job_rejects_backslashes():
    """build_queue_job rejects event_type with backslashes."""
    with pytest.raises(ValueError, match="contains invalid characters"):
        build_queue_job({"event_type": "path\\to\\file"})


def test_build_queue_job_rejects_dotdot():
    """build_queue_job rejects event_type with .."""
    with pytest.raises(ValueError, match="contains invalid characters"):
        build_queue_job({"event_type": "../escape"})


def test_build_queue_job_rejects_spaces():
    """build_queue_job rejects event_type with spaces."""
    with pytest.raises(ValueError, match="contains invalid characters"):
        build_queue_job({"event_type": "has space"})


def test_build_queue_job_accepts_valid_event_types():
    """build_queue_job accepts valid event_type patterns."""
    valid_types = ["ip_enrichment", "daily-report", "test.playbook", "UPPER_case", "a_b-c.d"]
    for event_type in valid_types:
        job = build_queue_job({"event_type": event_type})
        assert job["event_type"] == event_type


# resolve_script_path tests


def test_resolve_script_path_resolves_correctly(tmp_path: Path):
    """resolve_script_path resolves event_type to musicsheets/event_type.py."""
    musicsheets = tmp_path / "musicsheets"
    musicsheets.mkdir()
    script = musicsheets / "ip_enrichment.py"
    script.write_text("# test")

    result = resolve_script_path(tmp_path, "ip_enrichment")
    assert result == script.resolve()


def test_resolve_script_path_rejects_traversal(tmp_path: Path):
    """resolve_script_path rejects event_type that escapes musicsheets/."""
    musicsheets = tmp_path / "musicsheets"
    musicsheets.mkdir()

    with pytest.raises(ValueError, match="path escapes musicsheets/ directory"):
        resolve_script_path(tmp_path, "../escape")


def test_resolve_script_path_rejects_nested_traversal(tmp_path: Path):
    """resolve_script_path rejects deeply nested traversal attempts."""
    musicsheets = tmp_path / "musicsheets"
    musicsheets.mkdir()

    with pytest.raises(ValueError, match="path escapes musicsheets/ directory"):
        resolve_script_path(tmp_path, "subdir/../../escape")


# execute_job tests


def test_execute_job_missing_script(tmp_path: Path):
    """execute_job returns missing_script status when script doesn't exist."""
    musicsheets = tmp_path / "musicsheets"
    musicsheets.mkdir()

    job = {"event_type": "nonexistent", "payload": {}}
    result = execute_job(job, project_root=tmp_path)

    assert result["status"] == "missing_script"
    assert result["event_type"] == "nonexistent"


def test_execute_job_success(tmp_path: Path):
    """execute_job returns success for scripts that exit 0."""
    musicsheets = tmp_path / "musicsheets"
    musicsheets.mkdir()

    script = musicsheets / "success.py"
    script.write_text("print('hello')")

    job = {"event_type": "success", "payload": {}}
    result = execute_job(job, project_root=tmp_path)

    assert result["status"] == "success"
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]


def test_execute_job_failed(tmp_path: Path):
    """execute_job returns failed for scripts that exit non-zero."""
    musicsheets = tmp_path / "musicsheets"
    musicsheets.mkdir()

    script = musicsheets / "fail.py"
    script.write_text("import sys; sys.exit(1)")

    job = {"event_type": "fail", "payload": {}}
    result = execute_job(job, project_root=tmp_path)

    assert result["status"] == "failed"
    assert result["returncode"] == 1


def test_execute_job_timeout(tmp_path: Path):
    """execute_job returns timeout for scripts that exceed timeout."""
    musicsheets = tmp_path / "musicsheets"
    musicsheets.mkdir()

    script = musicsheets / "slow.py"
    script.write_text("import time; time.sleep(10)")

    job = {"event_type": "slow", "payload": {}}
    result = execute_job(job, project_root=tmp_path, timeout_seconds=1)

    assert result["status"] == "timeout"
    assert result["timeout_seconds"] == 1


def test_execute_job_passes_payload_via_stdin(tmp_path: Path):
    """execute_job passes payload as JSON via stdin."""
    musicsheets = tmp_path / "musicsheets"
    musicsheets.mkdir()

    script = musicsheets / "echo_payload.py"
    script.write_text("import sys; print(sys.stdin.read())")

    job = {"event_type": "echo_payload", "payload": {"key": "value"}}
    result = execute_job(job, project_root=tmp_path)

    assert result["status"] == "success"
    assert '"key": "value"' in result["stdout"]


# push_dlq_record tests


def test_push_dlq_record_excludes_raw_payload():
    """push_dlq_record strips payload from the stored job."""
    fake = FakeRedis()
    raw_job = json.dumps({
        "job_id": "abc123",
        "event_type": "test",
        "payload": {"secret": "password123"},
        "metadata": {"source": "webhook"},
    })
    result = {"status": "failed", "returncode": 1, "stdout": "output", "stderr": "error"}

    push_dlq_record(fake, "orchestra:dlq", raw_job, result)

    assert len(fake.items) == 1
    key, stored = fake.items[0]
    assert key == "orchestra:dlq"

    record = json.loads(stored)
    stored_job = json.loads(record["raw_job"])

    # Payload should be stripped
    assert "payload" not in stored_job
    assert stored_job["job_id"] == "abc123"
    assert stored_job["event_type"] == "test"
    assert stored_job["metadata"] == {"source": "webhook"}


def test_push_dlq_record_excludes_stdout_stderr():
    """push_dlq_record strips stdout and stderr from the result."""
    fake = FakeRedis()
    raw_job = json.dumps({"job_id": "abc123", "event_type": "test", "payload": {}, "metadata": {}})
    result = {
        "status": "failed",
        "returncode": 1,
        "stdout": "sensitive output",
        "stderr": "error details",
    }

    push_dlq_record(fake, "orchestra:dlq", raw_job, result)

    record = json.loads(fake.items[0][1])
    assert "stdout" not in record["result"]
    assert "stderr" not in record["result"]
    assert record["result"]["status"] == "failed"
    assert record["result"]["returncode"] == 1


def test_push_dlq_record_includes_required_fields():
    """push_dlq_record includes job_id, event_type, metadata, result, and failed_at."""
    fake = FakeRedis()
    raw_job = json.dumps({
        "job_id": "abc123",
        "event_type": "test",
        "payload": {"data": "value"},
        "metadata": {"source": "webhook", "received_at": 1234567890},
    })
    result = {"status": "failed", "returncode": 1}

    push_dlq_record(fake, "orchestra:dlq", raw_job, result)

    record = json.loads(fake.items[0][1])
    assert record["job_id"] == "abc123"
    assert "failed_at" in record
    assert isinstance(record["failed_at"], int)

    stored_job = json.loads(record["raw_job"])
    assert stored_job["event_type"] == "test"
    assert stored_job["metadata"]["source"] == "webhook"


def test_push_dlq_record_handles_invalid_json():
    """push_dlq_record handles invalid JSON gracefully."""
    fake = FakeRedis()
    raw_job = "not valid json"
    result = {"status": "invalid_job", "error": "parse error"}

    push_dlq_record(fake, "orchestra:dlq", raw_job, result)

    assert len(fake.items) == 1
    record = json.loads(fake.items[0][1])
    stored_job = json.loads(record["raw_job"])
    assert stored_job == {"invalid": True}
