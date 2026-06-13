"""CLI wrappers for the ``orchestra jobs failed`` commands."""

import json
import sys
from datetime import datetime
from pathlib import Path

from conductor.conductor_tasks.failed_jobs import (
    export_failed_jobs as _export_failed_jobs,
)
from conductor.conductor_tasks.failed_jobs import (
    find_failed_job,
)
from conductor.conductor_tasks.failed_jobs import (
    list_failed_jobs as _list_failed_jobs,
)
from conductor.conductor_tasks.failed_jobs import (
    purge_failed_jobs as _purge_failed_jobs,
)
from conductor.conductor_tasks.failed_jobs import (
    replay_failed_job as _replay_failed_job,
)
from orchestra_core.config import load_musician_config
from orchestra_core.redis import get_redis_client

# Column widths for the compact list table
_JOB_ID_WIDTH = 34
_EVENT_TYPE_WIDTH = 18
_STATUS_WIDTH = 12


def _load_failed_jobs_context():
    """Resolve Redis client and both Redis keys from musician config."""
    config = load_musician_config()
    redis_client = get_redis_client()
    return redis_client, config["queue_key"], config["dlq_key"]


def _format_failed_at(timestamp) -> str:
    """Render a failed_at epoch timestamp as a readable local string."""
    if not isinstance(timestamp, (int, float)):
        return str(timestamp)
    return datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")


def _extract_table_field(record: dict, key: str) -> str:
    """Safely extract a top-level or nested field for the table view."""
    value = record.get(key)
    if value is not None:
        return str(value)
    raw_job = record.get("raw_job")
    if isinstance(raw_job, dict):
        value = raw_job.get(key)
        if value is not None:
            return str(value)
    elif isinstance(raw_job, str):
        try:
            parsed = json.loads(raw_job)
        except json.JSONDecodeError:
            return ""
        if isinstance(parsed, dict):
            value = parsed.get(key)
            if value is not None:
                return str(value)
    return ""


def list_failed_jobs() -> None:
    """Print a compact table of failed jobs.

    Malformed records are skipped with a one-line warning. The
    operator inspects Redis directly to recover them.
    """
    try:
        redis_client, _queue_key, dlq_key = _load_failed_jobs_context()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    records = _list_failed_jobs(redis_client, dlq_key)

    well_formed = [r for r in records if not r.get("malformed")]
    malformed_count = len(records) - len(well_formed)

    if not well_formed:
        if malformed_count:
            print(
                f"Warning: {malformed_count} malformed record(s) skipped. "
                "Inspect Redis directly to recover."
            )
        else:
            print("(No failed jobs)")
        return

    header = (
        f"  {'INDEX':<5} {'JOB_ID':<{_JOB_ID_WIDTH}} "
        f"{'EVENT_TYPE':<{_EVENT_TYPE_WIDTH}} "
        f"{'STATUS':<{_STATUS_WIDTH}} FAILED_AT"
    )
    print("\n--- Failed Jobs ---\n")
    print(header)
    for index, record in enumerate(well_formed):
        job_id = _extract_table_field(record, "job_id")
        event_type = _extract_table_field(record, "event_type")
        result = record.get("result") or {}
        status = result.get("status", "")
        failed_at = _format_failed_at(record.get("failed_at"))
        print(
            f"  {index:<5} {job_id:<{_JOB_ID_WIDTH}} "
            f"{event_type:<{_EVENT_TYPE_WIDTH}} "
            f"{status:<{_STATUS_WIDTH}} {failed_at}"
        )
    print()
    if malformed_count:
        print(
            f"Warning: {malformed_count} malformed record(s) skipped. "
            "Inspect Redis directly to recover."
        )


def show_failed_job(ref: str) -> None:
    """Print one failed job record as pretty JSON."""
    try:
        redis_client, _queue_key, dlq_key = _load_failed_jobs_context()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    records = _list_failed_jobs(redis_client, dlq_key)

    found = find_failed_job(records, ref)
    if found is None:
        print(f"Error: No failed job found for '{ref}'.", file=sys.stderr)
        sys.exit(1)
    _index, record = found
    print(json.dumps(record, indent=2, sort_keys=True))


def replay_failed_job(ref: str) -> None:
    """Replay a failed job if its original job payload is available."""
    try:
        redis_client, queue_key, dlq_key = _load_failed_jobs_context()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    records = _list_failed_jobs(redis_client, dlq_key)

    found = find_failed_job(records, ref)
    if found is None:
        print(f"Error: No failed job found for '{ref}'.", file=sys.stderr)
        sys.exit(1)
    _index, record = found

    replayed, job_id, error = _replay_failed_job(redis_client, queue_key, record)
    if not replayed:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Failed job replayed to queue: {job_id}")


def purge_failed_jobs(yes: bool = False) -> None:
    """Purge failed job records after explicit confirmation."""
    if not yes:
        print(
            "Error: Refusing to purge failed jobs without --yes.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        redis_client, _queue_key, dlq_key = _load_failed_jobs_context()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    count = _purge_failed_jobs(redis_client, dlq_key)
    print(f"[+] Purged {count} failed job record(s) from {dlq_key}")


def export_failed_jobs(output: str | None = None) -> None:
    """Export failed job records as JSON to stdout or a file."""
    try:
        redis_client, _queue_key, dlq_key = _load_failed_jobs_context()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    records = _list_failed_jobs(redis_client, dlq_key)
    json_text = _export_failed_jobs(records)

    if output:
        Path(output).write_text(json_text)
        print(f"[+] Exported {len(records)} record(s) to {output}")
    else:
        sys.stdout.write(json_text)
