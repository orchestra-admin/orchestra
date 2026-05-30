from typing import TYPE_CHECKING

from orchestra_core.config import get_project_root, load_musician_config

if TYPE_CHECKING:
    import redis


def get_redis_client() -> "redis.Redis":
    """Create and return a Redis client connected to the configured instance."""
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError(
            "redis package is required to run the Orchestra musician."
        ) from exc

    project_root = get_project_root()
    config = load_musician_config(project_root)
    return redis.Redis(
        host=config["host"],
        port=config["port"],
        db=config["db"],
        decode_responses=True,
    )
