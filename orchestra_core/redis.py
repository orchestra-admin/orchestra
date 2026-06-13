from typing import TYPE_CHECKING

from orchestra_core.config import get_project_root, load_musician_config

if TYPE_CHECKING:
    import redis


def get_redis_client() -> "redis.Redis":
    """Create and return a Redis client, verified reachable.

    Performs a ping at construction so callers get a clear
    RuntimeError with remediation hints instead of a stack trace
    from the first command that actually tries to talk to Redis.
    """
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError(
            "redis package is required to run the Orchestra musician."
        ) from exc

    project_root = get_project_root()
    config = load_musician_config(project_root)
    client = redis.Redis(
        host=config["host"],
        port=config["port"],
        db=config["db"],
        decode_responses=True,
    )
    try:
        client.ping()
    except redis.exceptions.ConnectionError as exc:
        host = config["host"]
        port = config["port"]
        raise RuntimeError(
            f"Redis is not reachable at {host}:{port}. "
            f"Start it with `docker compose up -d redis`."
        ) from exc
    return client
