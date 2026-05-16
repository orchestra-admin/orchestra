import json
import subprocess
import sys
import time
from pathlib import Path

from orchestra_core.config import (
    DEFAULT_DLQ_KEY,
    DEFAULT_TIMEOUT_SECONDS,
    DEACTIVATED_SET_KEY,
    get_project_root,
    get_project_config_path,
    load_musician_config,
)
from orchestra_core.redis import get_redis_client
import logging

logger = logging.getLogger(__name__)


def parse_job(raw_job: str) -> dict:
    """Parse and validate a raw JSON job string into a structured job dictionary."""
    try:
        job = json.loads(raw_job)
    except json.JSONDecodeError as exc:
        raise ValueError("Job must be valid JSON.") from exc

    if not isinstance(job, dict):
        raise ValueError("Job must be a JSON object.")

    event_type = job.get("event_type")
    payload = job.get("payload")
    metadata = job.get("metadata", {})

    if not isinstance(event_type, str) or not event_type:
        raise ValueError("Job must include a non-empty string field 'event_type'.")
    if not isinstance(payload, dict):
        raise ValueError("Job must include an object field 'payload'.")
    if not isinstance(metadata, dict):
        raise ValueError("Job field 'metadata' must be an object.")

    return {
        "event_type": event_type,
        "payload": payload,
        "metadata": metadata,
    }

def build_queue_job(payload: dict, source: str = "webhook", metadata: dict | None = None) -> dict:
    """Build a job dictionary from a payload with source metadata for enqueuing."""
    event_type = payload.get("event_type")
    if not isinstance(event_type, str) or not event_type:
        raise ValueError("Payload must include a non-empty string field 'event_type'.")

    job_metadata = {
        "source": source,
        "received_at": int(time.time()),
    }
    if metadata:
        job_metadata.update(metadata)

    return {
        "event_type": event_type,
        "payload": payload,
        "metadata": job_metadata,
    }

def enqueue_job(redis_client, queue_key: str, job: dict) -> None:
    """Validate and push a job onto the specified Redis queue."""
    raw_job = json.dumps(job)
    parse_job(raw_job)
    redis_client.rpush(queue_key, raw_job)

def resolve_script_path(project_root: Path, event_type: str) -> Path:
    """Resolve the musicsheet script file path for a given event type."""
    return project_root / "musicsheets" / f"{event_type}.py"

def execute_job(
    job: dict,
    project_root: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Execute a job's musicsheet script as a subprocess and return the result."""
    project_root = project_root or get_project_root()
    script_path = resolve_script_path(project_root, job["event_type"])

    if not script_path.exists():
        return {
            "status": "missing_script",
            "event_type": job["event_type"],
            "script_path": str(script_path),
        }

    payload_json = json.dumps(job["payload"])

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=payload_json,
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "event_type": job["event_type"],
            "script_path": str(script_path),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timeout_seconds": timeout_seconds,
        }

    status = "success" if result.returncode == 0 else "failed"
    return {
        "status": status,
        "event_type": job["event_type"],
        "script_path": str(script_path),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

def push_dlq_record(redis_client, dlq_key: str, raw_job: str, result: dict) -> None:
    """Record a failed job and its result to the dead letter queue in Redis."""
    record = {
        "raw_job": raw_job,
        "result": result,
        "failed_at": int(time.time()),
    }
    redis_client.rpush(dlq_key, json.dumps(record))

def process_raw_job(
    redis_client,
    raw_job: str,
    dlq_key: str = DEFAULT_DLQ_KEY,
    project_root: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Process a raw job through validation, deactivation check, execution, and DLQ handling."""
    try:
        job = parse_job(raw_job)
    except ValueError as exc:
        result = {
            "status": "invalid_job",
            "error": str(exc),
        }
        push_dlq_record(redis_client, dlq_key, raw_job, result)
        logger.error("musician.job.invalid", extra={"data": {"error": str(exc)}})
        return result

    if redis_client.sismember(DEACTIVATED_SET_KEY, job["event_type"]):
        result = {
            "status": "playbook_deactivated",
            "event_type": job["event_type"],
            "failure_reason": "playbook_deactivated",
        }
        push_dlq_record(redis_client, dlq_key, raw_job, result)
        logger.info("musician.job.skipped_deactivated", extra={"data": {"event_type": job["event_type"]}})
        return result

    result = execute_job(job, project_root=project_root, timeout_seconds=timeout_seconds)
    status = result["status"]

    if status == "success":
        logger.info("musician.job.completed", extra={"data": job})
        return result

    if status == "missing_script":
        logger.warning("musician.job.skipped_missing", extra={"data": {"event_type": job["event_type"]}})
        return result

    push_dlq_record(redis_client, dlq_key, raw_job, result)
    logger.warning("musician.job.dlq", extra={"data": {"event_type": job["event_type"], "status": status}})
    return result

def run_musician() -> int:
    """Run the musician loop that pulls and executes jobs from the Redis queue."""
    from orchestra_core.logging import setup_logging
    setup_logging()

    project_root = get_project_root()
    musician_config = load_musician_config(project_root)
    queue_key = musician_config["queue_key"]
    dlq_key = musician_config["dlq_key"]
    timeout_seconds = musician_config["timeout_seconds"]
    block_seconds = musician_config["block_seconds"]

    redis_client = get_redis_client()
    redis_client.ping()

    print(f"[*] Orchestra musician started")
    print(f"[*] Project root: {project_root}")
    print(f"[*] Config: {get_project_config_path(project_root)}")
    print(f"[*] Queue: {queue_key}")
    print(f"[*] DLQ: {dlq_key}")
    logger.info("musician.started", extra={"data": {"project_root": str(project_root), "queue": queue_key, "dlq": dlq_key}})

    while True:
        item = redis_client.blpop(queue_key, timeout=block_seconds)
        if item is None:
            continue

        _, raw_job = item
        process_raw_job(
            redis_client,
            raw_job,
            dlq_key=dlq_key,
            project_root=project_root,
            timeout_seconds=timeout_seconds,
        )
