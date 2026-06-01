import sys
from pathlib import Path
from typing import TYPE_CHECKING

from composer_agent.composer_tasks.review import review_playbook as _review_playbook
from conductor.conductor_tasks.musician import build_queue_job, execute_job
from orchestra_core.config import (
    DEACTIVATED_SET_KEY,
    get_project_root,
)
from orchestra_core.exceptions import OrchestraError
from orchestra_core.redis import get_redis_client

if TYPE_CHECKING:
    import redis


def is_playbook_deactivated(redis_client: "redis.Redis", event_type: str) -> bool:
    """Check whether a playbook is currently deactivated in Redis."""
    return redis_client.sismember(DEACTIVATED_SET_KEY, event_type)


def deactivate_playbook(event_type: str) -> None:
    """Deactivate a playbook so its incoming jobs are sent to the DLQ."""
    redis_client = get_redis_client()
    project_root = get_project_root()
    script_path = project_root / "musicsheets" / f"{event_type}.py"

    if not script_path.exists():
        print(
            f"[!] Warning: No musicsheet found for '{event_type}', "
            "but writing to Redis anyway."
        )

    if redis_client.sismember(DEACTIVATED_SET_KEY, event_type):
        print(f"[*] Playbook '{event_type}' is already inactive.")
        return

    redis_client.sadd(DEACTIVATED_SET_KEY, event_type)
    print(f"[-] Playbook '{event_type}' has been deactivated.")


def activate_playbook(event_type: str) -> None:
    """Reactivate a previously deactivated playbook."""
    redis_client = get_redis_client()

    if not redis_client.sismember(DEACTIVATED_SET_KEY, event_type):
        print(f"[*] Playbook '{event_type}' is already active.")
        return

    redis_client.srem(DEACTIVATED_SET_KEY, event_type)
    print(f"[+] Playbook '{event_type}' has been activated.")


def print_playbooks() -> None:
    """Print all available playbooks from the playbooks directory with their status."""
    project_root = get_project_root()
    playbooks_dir = project_root / "playbooks"

    print("\n--- Available Playbooks ---\n")

    if not playbooks_dir.exists():
        print("  (No playbooks directory found)")
        return

    playbooks = sorted(playbooks_dir.glob("*.md"))

    if not playbooks:
        print("  (No playbooks found)")
        return

    try:
        redis_client = get_redis_client()
        deactivated = redis_client.smembers(DEACTIVATED_SET_KEY)
    except Exception:
        deactivated = set()

    print(f"  {'PLAYBOOK':<30} STATUS")
    for playbook in playbooks:
        event_type = playbook.stem
        status = "inactive" if event_type in deactivated else "active"
        print(f"  {event_type:<30} {status}")

    print()


def run_playbook(event_type: str, payload: dict | None = None) -> None:
    """Manually execute a playbook by its event type with an optional payload."""
    payload = payload or {}
    payload["event_type"] = event_type

    try:
        job = build_queue_job(payload, source="manual")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return

    print(f"[*] Running playbook '{event_type}' manually...")
    result = execute_job(job)

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.status == "success":
        print(f"[+] Playbook '{event_type}' completed successfully.")
    elif result.status == "missing_script":
        print(
            f"[!] No musicsheet found for '{event_type}' at {result.script_path}"
        )
    elif result.status == "timeout":
        print(
            f"[!] Playbook '{event_type}' timed out after "
            f"{result.timeout_seconds}s."
        )
    else:
        returncode = result.returncode
        print(f"[!] Playbook '{event_type}' failed with exit code {returncode}.")


def review_playbook(playbook_path: str) -> None:
    """Review a playbook markdown file using the composer agent's reviewer."""
    playbook_file = Path(playbook_path)

    if not playbook_file.exists():
        print(f"Error: Playbook not found: {playbook_path}", file=sys.stderr)
        sys.exit(1)

    if not playbook_file.is_file():
        print(f"Error: Not a file: {playbook_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Reviewing playbook: {playbook_path}...")
    try:
        result = _review_playbook(playbook_path)
    except OrchestraError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(result)
