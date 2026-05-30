import json
import sys

from croniter import croniter

from orchestra_core.config import get_project_config_path


def _load_config() -> dict:
    """Load the project configuration from orchestra.json."""
    config_path = get_project_config_path()
    if not config_path.exists():
        return {}

    with open(config_path) as f:
        return json.load(f)


def _save_config(data: dict) -> None:
    """Save the project configuration to orchestra.json."""
    config_path = get_project_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def list_schedules() -> None:
    """Print all configured cron schedules from the project config."""
    data = _load_config()
    schedules = data.get("schedules", {})

    print("\n--- Scheduled Playbooks ---\n")

    if not schedules:
        print("  (No schedules configured)")
        print()
        return

    print(f"  {'EVENT_TYPE':<30} CRON")
    for event_type, cron_expr in sorted(schedules.items()):
        print(f"  {event_type:<30} {cron_expr}")

    print()


def add_schedule(event_type: str, cron_expr: str) -> None:
    """Add or update a cron schedule for the given event type."""
    if not croniter.is_valid(cron_expr):
        print(
            f"Error: Invalid cron expression '{cron_expr}'. Must be a valid 5-field cron expression.",
            file=sys.stderr,
        )
        sys.exit(1)

    data = _load_config()
    schedules = data.setdefault("schedules", {})

    schedules[event_type] = cron_expr
    _save_config(data)
    print(f"[+] Schedule set: '{event_type}' → '{cron_expr}'")


def remove_schedule(event_type: str) -> None:
    """Remove the cron schedule for the given event type."""
    data = _load_config()
    schedules = data.get("schedules", {})

    if event_type not in schedules:
        print(f"[*] No schedule found for '{event_type}'.")
        return

    del schedules[event_type]
    _save_config(data)
    print(f"[-] Schedule removed for '{event_type}'.")
