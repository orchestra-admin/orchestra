import json

from conductor_agent.conductor_tasks.config import get_project_config_path, get_project_root


def _load_config():
    config_path = get_project_config_path()
    if not config_path.exists():
        return {}

    with open(config_path, "r") as f:
        return json.load(f)


def _save_config(data: dict):
    config_path = get_project_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def list_schedules():
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


def add_schedule(event_type: str, cron_expr: str):
    data = _load_config()
    schedules = data.setdefault("schedules", {})

    schedules[event_type] = cron_expr
    _save_config(data)
    print(f"[+] Schedule set: '{event_type}' → '{cron_expr}'")


def remove_schedule(event_type: str):
    data = _load_config()
    schedules = data.get("schedules", {})

    if event_type not in schedules:
        print(f"[*] No schedule found for '{event_type}'.")
        return

    del schedules[event_type]
    _save_config(data)
    print(f"[-] Schedule removed for '{event_type}'.")
