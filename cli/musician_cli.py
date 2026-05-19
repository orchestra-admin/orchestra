import sys

from conductor.conductor_tasks.musician import run_musician as _run_musician


def run_musician() -> int:
    """CLI wrapper to run the Orchestra musician job processor."""

    print("[*] Orchestra musician started")
    try:
        return _run_musician()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
