import sys

from conductor.conductor_tasks.scheduler import run_scheduler as _run_scheduler


def run_scheduler() -> None:
    """CLI wrapper to run the Orchestra scheduler engine."""
    print("[*] Orchestra scheduler started")
    try:
        _run_scheduler()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
