"""Service helpers for reading, finding, exporting, purging, and replaying failed jobs.

Storage backend: Redis list at the key configured by `musician.dlq_key`.
User-facing language is "failed jobs" (not DLQ).
Replay is allowed only for records that explicitly contain a `replay_job`.
"""

import json

from conductor.conductor_tasks.musician import enqueue_job, parse_job


def list_failed_jobs(redis_client, dlq_key: str) -> list[dict]:
    """Return parsed failed job records from the failed jobs store.

    Malformed records (invalid JSON or non-dict) are tagged with
    ``{"malformed": True, "raw": <original>}`` so the CLI can decide
    how to present them.
    """
    records = []
    for raw in redis_client.lrange(dlq_key, 0, -1):
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            records.append({"malformed": True, "raw": raw})
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            records.append({"malformed": True, "raw": raw})
    return records


def _parse_raw_job(record: dict) -> dict:
    """Parse a record's raw_job field, which may be a dict or a JSON string."""
    raw_job = record.get("raw_job")
    if isinstance(raw_job, dict):
        return raw_job
    if isinstance(raw_job, str):
        try:
            parsed = json.loads(raw_job)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def find_failed_job(records: list[dict], ref: str) -> tuple[int, dict] | None:
    """Find a failed job by numeric index or job_id.

    Returns (index, record) or None if not found.
    """
    if not isinstance(ref, str):
        return None

    if ref.isdigit():
        index = int(ref)
        if 0 <= index < len(records):
            return (index, records[index])
        return None

    for index, record in enumerate(records):
        if record.get("malformed"):
            continue
        if record.get("job_id") == ref:
            return (index, record)
        raw_job = _parse_raw_job(record)
        if raw_job.get("job_id") == ref:
            return (index, record)
    return None


def export_failed_jobs(records: list[dict]) -> str:
    """Serialize failed job records as pretty JSON."""
    return json.dumps(records, indent=2, sort_keys=True) + "\n"


def purge_failed_jobs(redis_client, dlq_key: str) -> int:
    """Delete all failed job records and return the deleted count."""
    count = redis_client.llen(dlq_key)
    redis_client.delete(dlq_key)
    return int(count)


def is_replayable_failed_job(record: dict) -> bool:
    """Return whether a failed job record contains enough original job data to replay."""
    if not isinstance(record, dict):
        return False
    replay_job = record.get("replay_job")
    if not isinstance(replay_job, dict):
        return False
    try:
        parse_job(json.dumps(replay_job))
    except ValueError:
        return False
    return True


def replay_failed_job(
    redis_client,
    queue_key: str,
    record: dict,
) -> tuple[bool, str | None, str | None]:
    """Replay a failed job if possible by pushing it back to the normal queue.

    Returns (replayed, job_id, error). If the record is not replayable,
    the second and third elements are None and an error message.
    """
    if not is_replayable_failed_job(record):
        return (
            False,
            None,
            "Failed job is not replayable because its original payload was not retained.",
        )

    replay_job = record["replay_job"]
    enqueue_job(redis_client, queue_key, replay_job)
    return (True, replay_job.get("job_id"), None)
