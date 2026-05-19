import importlib
import inspect
import json
import re
import sys
from pathlib import Path
import logging

from orchestra_core.config import ACTIONS_DIR

logger = logging.getLogger(__name__)

GET_SECRET_PATTERN = re.compile(r'get_secret\("([^"]+)"\)')


def _extract_secret_keys(filepath: Path) -> list[str]:
    """Scan a Python source file for get_secret("<KEY>") call and return the key names."""
    keys = set()
    try:
        with open(filepath, "r") as f:
            source = f.read()
        for key in GET_SECRET_PATTERN.findall(source):
            keys.add(key)
    except Exception:
        pass
    return sorted(keys)


def _build_func_index_from_dir(directory: Path, module_prefix: str, output_json_path: Path) -> dict:
    """Scan .py files in a directory and return a grouped dict index with module name as key.

    Each module entry contains a secrets list extracted from get_secret() calls
    and a functions list with signatures and docstrings for each public function.
    Writes the resulting dict to disk at output_json_path.
    """
    if not directory.exists():
        return {}

    grouped: dict = {}

    for file in directory.glob("*.py"):
        if file.name.startswith("__"):
            continue

        secret_keys = _extract_secret_keys(file)

        module_name = f"{module_prefix}.{file.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            logger.warning("index.import_failed", extra={"data": {"module": module_name, "error": str(e)}})
            continue

        functions = []
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("_") and getattr(obj, "__module__", "") == module.__name__:
                sig = str(inspect.signature(obj))
                doc = inspect.getdoc(obj)

                description = ""
                if doc:
                    description = doc.strip().split('\n\n')[0].replace('\n', ' ').strip()

                functions.append({
                    "function": name,
                    "signature": sig,
                    "description": description,
                })

        if functions:
            grouped[module_name] = {"secrets": secret_keys, "functions": functions}

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w") as f:
        json.dump(grouped, f, indent=4)

    return grouped


def build_action_index(project_root: Path) -> dict:
    """Build and merge built-in + local action indexes into a single grouped dict."""
    musicsheets_path = str(project_root / "musicsheets")
    if musicsheets_path not in sys.path:
        sys.path.insert(0, musicsheets_path)

    local_base = project_root / "musicsheets" / "local_actions"

    actions = _build_func_index_from_dir(ACTIONS_DIR, "actions", local_base / "builtin_action_index.json")
    actions.update(_build_func_index_from_dir(local_base, "local_actions", local_base / "local_action_index.json"))
    return actions


def build_integration_index(project_root: Path) -> dict:
    """Build and merge built-in + local integration indexes into a single grouped dict."""
    musicsheets_path = str(project_root / "musicsheets")
    if musicsheets_path not in sys.path:
        sys.path.insert(0, musicsheets_path)

    local_base = project_root / "musicsheets" / "local_actions" / "local_integrations"

    integrations = _build_func_index_from_dir(ACTIONS_DIR / "integrations", "actions.integrations", local_base / "builtin_integration_index.json")
    integrations.update(_build_func_index_from_dir(local_base, "local_actions.local_integrations", local_base / "local_integration_index.json"))
    return integrations