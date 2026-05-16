import sys
from pathlib import Path

from composer_agent.composer import compose
from orchestra_core.exceptions import OrchestraError


def compose_playbook(playbook_path: str) -> None:
    """Compose a Python script from a playbook markdown file."""
    playbook_path = Path(playbook_path)
    if not playbook_path.exists():
        print(f"Error: Playbook not found: {playbook_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Composing script for {playbook_path}...")
    try:
        ok, path, error = compose("playbook", playbook=playbook_path)
    except OrchestraError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not ok:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Output written to {path}")


def compose_action(description: str, name: str | None = None) -> None:
    """Generate an action Python module from a natural language description."""
    print(f"[*] Generating action: {description}")
    try:
        ok, path, msg = compose("action", description=description, name=name)
    except OrchestraError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not ok:
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)
    if path:
        print(f"[+] Action written to local_actions/{Path(path).name}")
    else:
        print(f"[*] {msg}")


def compose_integration(description: str, name: str | None = None) -> None:
    """Generate an integration Python module from a natural language description."""
    print(f"[*] Generating integration: {description}")
    try:
        ok, path, msg = compose("integration", description=description, name=name)
    except OrchestraError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not ok:
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)
    if path:
        print(f"[+] Integration written to local_actions/local_integrations/{Path(path).name}")
    else:
        print(f"[*] {msg}")


def compose_integration(description: str, name: str | None = None) -> None:
    """CLI wrapper to generate an integration module from a natural language description."""
    print(f"[*] Generating integration: {description}")
    ok, path, msg = compose("integration", description=description, name=name)
    if not ok:
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)
    if path:
        print(f"[+] Integration written to local_actions/local_integrations/{Path(path).name}")
    else:
        print(f"[*] {msg}")
