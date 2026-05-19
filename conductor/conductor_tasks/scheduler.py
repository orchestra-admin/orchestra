import time
from datetime import datetime

from croniter import croniter

from orchestra_core.config import (
    DEACTIVATED_SET_KEY,
    get_project_config_path,
    get_project_root,
    load_musician_config,
    load_project_config,
)
from orchestra_core.redis import get_redis_client
from orchestra_core.logging import setup_logging
from conductor.conductor_tasks.musician import (
    build_queue_job,
    enqueue_job,
)
import logging

logger = logging.getLogger(__name__)


def load_schedules() -> dict:
    """Load the schedule configuration from the project config file."""
    return load_project_config().get("schedules", {})


def run_scheduler() -> None:
    """Run the scheduler loop that enqueues scheduled jobs on their cron intervals."""
    setup_logging()

    project_root = get_project_root()
    musician_config = load_musician_config(project_root)
    queue_key = musician_config["queue_key"]

    redis_client = get_redis_client()
    redis_client.ping()

    logger.info("scheduler.started", extra={"data": {"project_root": str(project_root), "queue": queue_key}})

    last_fired: dict[str, str] = {}

    while True:
        now = datetime.now()
        current_minute = now.strftime("%Y%m%d%H%M")
        schedules = load_schedules()

        for event_type, cron_expr in schedules.items():
            if not croniter.is_valid(cron_expr):
                logger.warning("scheduler.cron.invalid_expression", extra={"data": {"event_type": event_type, "cron": cron_expr}})
                continue

            if not croniter.match(cron_expr, now):
                continue

            if last_fired.get(event_type) == current_minute:
                continue
            last_fired[event_type] = current_minute

            if redis_client.sismember(DEACTIVATED_SET_KEY, event_type):
                continue

            payload = {"event_type": event_type}
            try:
                job = build_queue_job(payload, source="schedule")
            except ValueError:
                logger.warning("scheduler.cron.skipped_invalid", extra={"data": {"event_type": event_type}})
                continue
            enqueue_job(redis_client, queue_key, job)
            logger.info("scheduler.cron.fired", extra={"data": {"event_type": event_type, "cron": cron_expr}})

        sleep_seconds = 60 - datetime.now().second
        time.sleep(sleep_seconds)
