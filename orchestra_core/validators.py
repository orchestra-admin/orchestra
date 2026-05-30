import re
from pathlib import Path

from orchestra_core.config import EVENT_TYPE_PATTERN


def validate_event_type(event_type: str) -> None:
    """Validate that an event type string is non-empty and contains only safe characters."""
    if not isinstance(event_type, str) or not event_type:
        raise ValueError("Payload must include a non-empty string field 'event_type'.")
    if not EVENT_TYPE_PATTERN.match(event_type):
        raise ValueError(
            f"Payload event_type '{event_type}' contains invalid characters. "
            f"Only alphanumeric characters, underscores, hyphens, and dots are allowed."
        )


def safe_child_path(base_dir: Path, relative_path: str) -> Path:
    """Safely resolve a child path and ensure it doesn't escape the base directory."""
    if ".." in relative_path or "/" in relative_path or "\\" in relative_path:
        raise ValueError(
            f"Invalid filename '{relative_path}': path traversal characters are not allowed"
        )
    target = (base_dir / relative_path).resolve()
    try:
        target.relative_to(base_dir.resolve())
    except ValueError:
        raise ValueError(
            f"Invalid filename '{relative_path}': path escapes base directory"
        ) from None
    return target


def validate_secret_key_name(key: str) -> None:
    """Validate that a secret key name does not contain path traversal characters."""
    if "/" in key or "\\" in key or ".." in key:
        raise ValueError(f"Invalid secret key name: {key}")
