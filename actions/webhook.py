import json
import sys

# Exception to AGENTS.md "no module-level mutable state" rule:
# stdin can only be read once per subprocess. This cache ensures
# get_payload() can be called multiple times within a musicsheet.
_PAYLOAD_CACHE = None

def get_payload() -> dict:
    """Read the webhook JSON payload from stdin."""
    global _PAYLOAD_CACHE

    if _PAYLOAD_CACHE is None:
        raw = sys.stdin.read().strip() or "{}"
        _PAYLOAD_CACHE = json.loads(raw)

    return _PAYLOAD_CACHE
