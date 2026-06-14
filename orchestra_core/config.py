import json
import os
import re
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
ACTIONS_DIR = FRAMEWORK_ROOT / "actions"
INIT_ASSETS_DIR = FRAMEWORK_ROOT / "orchestra_core" / "init_assets"
DEFAULT_QUEUE_KEY = "orchestra:jobs"
DEFAULT_DLQ_KEY = "orchestra:dlq"
DEACTIVATED_SET_KEY = "orchestra:playbooks:deactivated"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_BLOCK_SECONDS = 5
MAX_WEBHOOK_BODY_BYTES = 1_048_576  # 1 MB
EVENT_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
DEFAULT_WEBHOOK_IDEMPOTENCY_TTL_SECONDS = 86400
DEFAULT_SCHEDULER_DEDUPE_TTL_SECONDS = 120
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
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

    with open(config_path) as f:
        return json.load(f)


def get_project_root() -> Path:
    """Find the Orchestra project root near the current working directory.

    The project root is identified by the presence of
    ``.local_config/orchestra.json``.  To avoid accidentally selecting a stale
    marker high in an ancestor tree, only the current directory and its
    immediate parent are considered.  If neither contains a marker, falls back
    to the current working directory.
    """
    marker = Path(".local_config") / "orchestra.json"
    current = Path.cwd()
    for candidate in (current, current.parent):
        if (candidate / marker).exists():
            return candidate
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


def load_dedupe_config(project_root: Path | None = None) -> dict:
    """Load dedupe settings from project config with defaults.

    Returns a flat dict with keys: webhook_idempotency_ttl_seconds,
    scheduler_ttl_seconds. Missing or invalid config falls back to
    the defaults defined at module level.
    """
    data = load_project_config(project_root)
    dedupe_cfg = data.get("dedupe", {})
    if not isinstance(dedupe_cfg, dict):
        dedupe_cfg = {}
    return {
        "webhook_idempotency_ttl_seconds": int(
            dedupe_cfg.get(
                "webhook_idempotency_ttl_seconds",
                DEFAULT_WEBHOOK_IDEMPOTENCY_TTL_SECONDS,
            )
        ),
        "scheduler_ttl_seconds": int(
            dedupe_cfg.get(
                "scheduler_ttl_seconds",
                DEFAULT_SCHEDULER_DEDUPE_TTL_SECONDS,
            )
        ),
    }
