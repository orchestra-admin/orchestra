import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON documents."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert a log record to a JSON string."""
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.msg),
            "data": getattr(record, "data", {}),
        }
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    """Configure the root logger to write JSON lines to logs/orchestra.log.

    Rotates at 10 MB with 5 backups (60 MB total).
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / "orchestra.log",
        maxBytes=10_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
