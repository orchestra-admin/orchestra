import json
from pathlib import Path

from orchestra_core.config import DEACTIVATED_SET_KEY, get_project_config_path
from orchestra_core.validators import validate_event_type


def load_deactivated_playbooks(project_root: Path) -> set[str]:
    """Load deactivated playbook event types from project config."""
    config_path = get_project_config_path(project_root)
    if not config_path.exists():
        return set()

    with open(config_path) as f:
        data = json.load(f)

    entries = data.get("playbooks", {}).get("deactivated", [])
    if not isinstance(entries, list):
        return set()
    return {str(e) for e in entries}


def is_playbook_deactivated(project_root: Path, event_type: str) -> bool:
    """Check whether a playbook is currently deactivated (durable config)."""
    return event_type in load_deactivated_playbooks(project_root)


def save_deactivated_playbooks(
    project_root: Path, event_types: set[str]
) -> None:
    """Persist deactivated playbook event types to project config."""
    for event_type in event_types:
        validate_event_type(event_type)

    config_path = get_project_config_path(project_root)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
    else:
        data = {}

    data.setdefault("playbooks", {})["deactivated"] = sorted(event_types)

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def deactivate_playbook_state(project_root: Path, event_type: str) -> bool:
    """Persist a deactivated playbook. Return True if state changed."""
    validate_event_type(event_type)

    current = load_deactivated_playbooks(project_root)
    if event_type in current:
        return False

    current.add(event_type)
    save_deactivated_playbooks(project_root, current)
    return True


def activate_playbook_state(project_root: Path, event_type: str) -> bool:
    """Persist an activated playbook. Return True if state changed."""
    validate_event_type(event_type)

    current = load_deactivated_playbooks(project_root)
    if event_type not in current:
        return False

    current.discard(event_type)
    save_deactivated_playbooks(project_root, current)
    return True


def sync_deactivated_playbooks(redis_client, project_root: Path) -> set[str]:
    """Replace Redis deactivation cache with durable config state."""
    durable = load_deactivated_playbooks(project_root)

    redis_client.delete(DEACTIVATED_SET_KEY)
    if durable:
        redis_client.sadd(DEACTIVATED_SET_KEY, *sorted(durable))

    return durable
