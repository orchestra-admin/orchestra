import json
import os
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
ACTIONS_DIR = FRAMEWORK_ROOT / "actions"
INIT_ASSETS_DIR = FRAMEWORK_ROOT / "orchestra_core" / "init_assets"
DEFAULT_QUEUE_KEY = "orchestra:jobs"
DEFAULT_DLQ_KEY = "orchestra:dlq"
DEACTIVATED_SET_KEY = "playbooks:deactivated"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_BLOCK_SECONDS = 5
DEFAULT_REDIS_CONFIG = {
    "host": "127.0.0.1",
    "port": 6379,
    "db": 0,
}
DEFAULT_MUSICIAN_RUNTIME_CONFIG = {
    "queue_key": DEFAULT_QUEUE_KEY,
    "dlq_key": DEFAULT_DLQ_KEY,
    "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
    "block_seconds": DEFAULT_BLOCK_SECONDS,
}
MUSICIAN_ENV_OVERRIDES = {
    "host": "ORCHESTRA_REDIS_HOST",
    "port": "ORCHESTRA_REDIS_PORT",
    "db": "ORCHESTRA_REDIS_DB",
    "queue_key": "ORCHESTRA_QUEUE_KEY",
    "dlq_key": "ORCHESTRA_DLQ_KEY",
    "timeout_seconds": "ORCHESTRA_TIMEOUT_SECONDS",
    "block_seconds": "ORCHESTRA_BLOCK_SECONDS",
}
INT_MUSICIAN_CONFIG_KEYS = {"port", "db", "timeout_seconds", "block_seconds"}


def load_project_config(project_root: Path | None = None) -> dict:
    """Read orchestra.json and return the parsed config dict."""
    config_path = get_project_config_path(project_root)
    if not config_path.exists():
        return {}

    with open(config_path, "r") as f:
        return json.load(f)


def get_project_root() -> Path:
    """Walk up from cwd to find the Orchestra project root.

    The project root is identified by the presence of
    ``.local_config/orchestra.json``.  If no marker is found,
    falls back to the current working directory.
    """
    marker = Path(".local_config") / "orchestra.json"
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / marker).exists():
            return parent
    return current


def get_project_config_path(project_root: Path | None = None) -> Path:
    """Return the absolute path to the project's ``orchestra.json``."""
    project_root = project_root or get_project_root()
    return project_root / ".local_config" / "orchestra.json"

def load_musician_config(project_root: Path | None = None) -> dict:
    """Build a merged config dict for Redis connection and job processing.

    Used by the musician, webhook server, scheduler, and playbook CLI
    to get everything needed to talk to Redis and execute jobs.

    Config is merged in ascending priority:
      1. Hardcoded defaults (DEFAULT_REDIS_CONFIG + DEFAULT_MUSICIAN_RUNTIME_CONFIG)
      2. Project config from orchestra.json ("redis" and "musician" sections)
      3. Environment variables (ORCHESTRA_REDIS_HOST, etc.) — highest priority,
         used by docker-compose to override host without editing orchestra.json

    Returns a flat dict with keys: host, port, db, queue_key, dlq_key,
    timeout_seconds, block_seconds.
    """
    config = dict(DEFAULT_REDIS_CONFIG)
    config.update(DEFAULT_MUSICIAN_RUNTIME_CONFIG)

    data = load_project_config(project_root)
    redis_cfg = data.get("redis", {})
    if isinstance(redis_cfg, dict):
        config.update(redis_cfg)
    musician_cfg = data.get("musician", {})
    if isinstance(musician_cfg, dict):
        config.update(musician_cfg)

    for key, env_name in MUSICIAN_ENV_OVERRIDES.items():
        raw_value = os.environ.get(env_name)
        if raw_value is None or raw_value == "":
            continue
        if key in INT_MUSICIAN_CONFIG_KEYS:
            config[key] = int(raw_value)
        else:
            config[key] = raw_value

    return config
