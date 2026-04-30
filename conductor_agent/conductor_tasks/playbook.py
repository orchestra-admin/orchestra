from pathlib import Path

from conductor_agent.conductor_tasks.config import (
    DEACTIVATED_SET_KEY,
    get_project_root,
    load_musician_config,
)
from conductor_agent.conductor_tasks.musician import load_redis_module


def _get_redis_client():
    project_root = get_project_root()
    musician_config = load_musician_config(project_root)
    redis = load_redis_module()
    return redis.Redis(
        host=musician_config["host"],
        port=musician_config["port"],
        db=musician_config["db"],
        decode_responses=True,
    )


def is_playbook_deactivated(redis_client, event_type: str) -> bool:
    return redis_client.sismember(DEACTIVATED_SET_KEY, event_type)


def deactivate_playbook(event_type: str) -> None:
    redis_client = _get_redis_client()
    project_root = get_project_root()
    script_path = project_root / "musicsheets" / f"{event_type}.py"

    if not script_path.exists():
        print(f"[!] Warning: No musicsheet found for '{event_type}', but writing to Redis anyway.")

    if redis_client.sismember(DEACTIVATED_SET_KEY, event_type):
        print(f"[*] Playbook '{event_type}' is already inactive.")
        return

    redis_client.sadd(DEACTIVATED_SET_KEY, event_type)
    print(f"[-] Playbook '{event_type}' has been deactivated.")


def activate_playbook(event_type: str) -> None:
    redis_client = _get_redis_client()

    if not redis_client.sismember(DEACTIVATED_SET_KEY, event_type):
        print(f"[*] Playbook '{event_type}' is already active.")
        return

    redis_client.srem(DEACTIVATED_SET_KEY, event_type)
    print(f"[+] Playbook '{event_type}' has been activated.")


def print_playbooks():
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
        redis_client = _get_redis_client()
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
    from conductor_agent.conductor_tasks.musician import build_queue_job, execute_job

    payload = payload or {}
    payload["event_type"] = event_type

    job = build_queue_job(payload, source="manual")

    print(f"[*] Running playbook '{event_type}' manually...")
    result = execute_job(job)
    status = result["status"]

    if result.get("stdout"):
        print(result["stdout"], end="")
    if result.get("stderr"):
        print(result["stderr"], end="", file=__import__("sys").stderr)

    if status == "success":
        print(f"[+] Playbook '{event_type}' completed successfully.")
    elif status == "missing_script":
        print(f"[!] No musicsheet found for '{event_type}' at {result['script_path']}")
    elif status == "timeout":
        print(f"[!] Playbook '{event_type}' timed out after {result['timeout_seconds']}s.")
    else:
        print(f"[!] Playbook '{event_type}' failed with exit code {result.get('returncode')}.")