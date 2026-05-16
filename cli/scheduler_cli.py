import sys


def run_scheduler() -> None:
    """CLI wrapper to run the Orchestra scheduler engine."""
    from conductor.conductor_tasks.scheduler import run_scheduler as _run

    try:
        _run()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
