import sys


def start_server(port: int = 8080) -> None:
    """CLI wrapper to start the Orchestra webhook server on the specified port."""
    from conductor.conductor_tasks.webhook import start_server as _start

    print(f"[*] Orchestra webhook server listening on port {port}")
    try:
        _start(port)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
