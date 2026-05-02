import json
import os
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent.parent
ACTIONS_DIR = FRAMEWORK_ROOT / "actions"
INIT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "init_assets"
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

def get_project_root() -> Path:
    marker = Path(".local_config") / "orchestra.json"
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / marker).exists():
            return parent
    return current

def get_project_config_path(project_root: Path | None = None) -> Path:
    project_root = project_root or get_project_root()
    return project_root / ".local_config" / "orchestra.json"

def load_musician_config(project_root: Path | None = None) -> dict:
    project_root = project_root or get_project_root()
    config = dict(DEFAULT_REDIS_CONFIG)
    config.update(DEFAULT_MUSICIAN_RUNTIME_CONFIG)
    config_path = get_project_config_path(project_root)

    if config_path.exists():
        with open(config_path, "r") as f:
            data = json.load(f)

        redis_config = data.get("redis", {})
        if isinstance(redis_config, dict):
            config.update(redis_config)

        musician_config = data.get("musician", {})
        if isinstance(musician_config, dict):
            config.update(musician_config)

    for key, env_name in MUSICIAN_ENV_OVERRIDES.items():
        raw_value = os.environ.get(env_name)
        if raw_value is None or raw_value == "":
            continue

        if key in INT_MUSICIAN_CONFIG_KEYS:
            config[key] = int(raw_value)
        else:
            config[key] = raw_value

    return config
