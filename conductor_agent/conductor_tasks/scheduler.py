import json
import time
from datetime import datetime

from conductor_agent.conductor_tasks.config import (
    DEACTIVATED_SET_KEY,
    get_project_config_path,
    get_project_root,
    load_musician_config,
)
from conductor_agent.conductor_tasks.musician import (
    load_redis_module,
    build_queue_job,
    enqueue_job,
)


def _match_cron_field(field: str, value: int, min_val: int, max_val: int) -> bool:
    """Check if a single cron field matches a given value."""
    if field == "*":
        return True

    for part in field.split(","):
        if "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            start = min_val if base == "*" else int(base)
            if (value - start) % step == 0 and value >= start:
                return True
        elif "-" in part:
            low, high = part.split("-", 1)
            if int(low) <= value <= int(high):
                return True
        else:
            if int(part) == value:
                return True

    return False


def is_due(cron_expr: str, now: datetime | None = None) -> bool:
    """Check if a 5-field cron expression matches the current minute."""
    now = now or datetime.now()
    fields = cron_expr.strip().split()

    if len(fields) != 5:
        return False

    minute, hour, day, month, weekday = fields

    return (
        _match_cron_field(minute, now.minute, 0, 59)
        and _match_cron_field(hour, now.hour, 0, 23)
        and _match_cron_field(day, now.day, 1, 31)
        and _match_cron_field(month, now.month, 1, 12)
        and _match_cron_field(weekday, now.weekday(), 0, 6)
    )


def load_schedules() -> dict:
    config_path = get_project_config_path()
    if not config_path.exists():
        return {}

    with open(config_path, "r") as f:
        data = json.load(f)

    return data.get("schedules", {})


def run_scheduler() -> None:
    project_root = get_project_root()
    musician_config = load_musician_config(project_root)
    host = musician_config["host"]
    port = musician_config["port"]
    db = musician_config["db"]
    queue_key = musician_config["queue_key"]

    redis = load_redis_module()
    redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    redis_client.ping()

    print(f"[*] Orchestra scheduler started on redis://{host}:{port}/{db}")
    print(f"[*] Project root: {project_root}")
    print(f"[*] Config: {get_project_config_path(project_root)}")
    print(f"[*] Queue: {queue_key}")

    while True:
        now = datetime.now()
        schedules = load_schedules()

        for event_type, cron_expr in schedules.items():
            if not is_due(cron_expr, now):
                continue

            if redis_client.sismember(DEACTIVATED_SET_KEY, event_type):
                continue

            payload = {"event_type": event_type}
            job = build_queue_job(payload, source="schedule")
            enqueue_job(redis_client, queue_key, job)
            print(f"[*] Scheduled job enqueued: {event_type}")

        # Sleep until the start of the next minute
        sleep_seconds = 60 - datetime.now().second
        time.sleep(sleep_seconds)
