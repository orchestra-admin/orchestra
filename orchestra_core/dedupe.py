"""Redis-backed deduplication helpers for webhook idempotency and scheduler fires."""

from orchestra_core.config import IDEMPOTENCY_KEY_PATTERN
from orchestra_core.validators import (
    validate_event_type,
    validate_idempotency_key,
)


def webhook_dedupe_key(key: str) -> str:
    """Build the Redis key for a webhook idempotency key."""
    if not isinstance(key, str) or not key:
        raise ValueError("Idempotency key must be a non-empty string.")
    if not IDEMPOTENCY_KEY_PATTERN.match(key):
        raise ValueError(
            "Idempotency key may contain only alphanumeric characters, "
            "underscores, hyphens, dots, and colons, up to 200 characters."
        )
    return f"orchestra:webhook:idempotency:{key}"


def scheduler_dedupe_key(event_type: str, minute_key: str) -> str:
    """Build the Redis key for a scheduled event/minute claim."""
    validate_event_type(event_type)
    if not isinstance(minute_key, str) or not minute_key:
        raise ValueError("Minute key must be a non-empty string.")
    return f"orchestra:scheduler:fired:{event_type}:{minute_key}"


def claim_webhook_idempotency_key(
    redis_client, key: str, job_id: str, ttl_seconds: int
) -> tuple[bool, str | None]:
    """Claim a webhook idempotency key.

    Returns (claimed, existing_job_id). If the key is fresh, returns
    (True, None) after storing the job_id with the given TTL. If the key
    is already claimed, returns (False, existing_job_id).
    """
    validate_idempotency_key(key)
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job_id must be a non-empty string.")
    if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be a positive integer.")

    redis_key = webhook_dedupe_key(key)
    claimed = redis_client.set(redis_key, job_id, nx=True, ex=ttl_seconds)
    if claimed:
        return (True, None)
    existing = redis_client.get(redis_key)
    if isinstance(existing, bytes):
        existing = existing.decode("utf-8")
    return (False, existing)


def claim_scheduler_fire(
    redis_client, event_type: str, minute_key: str, ttl_seconds: int
) -> bool:
    """Claim a scheduler fire slot for an event type and minute.

    Returns True if this caller is the first to claim the slot within
    the TTL window, False otherwise.
    """
    validate_event_type(event_type)
    if not isinstance(minute_key, str) or not minute_key:
        raise ValueError("Minute key must be a non-empty string.")
    if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be a positive integer.")

    redis_key = scheduler_dedupe_key(event_type, minute_key)
    return bool(redis_client.set(redis_key, "1", nx=True, ex=ttl_seconds))
