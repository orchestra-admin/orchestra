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


def _build_func_index_from_dir(directory: Path, module_prefix: str, output_json_name: str) -> dict:
    """Scan .py files in a directory and return a grouped dict index with module name as key.

    Each module entry contains a secrets list extracted from get_secret() calls
    and a functions list with signatures and docstrings for each public function.
    Writes the resulting dict to disk as JSON.
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

    index_path = directory / output_json_name
    with open(index_path, "w") as f:
        json.dump(grouped, f, indent=4)

    return grouped


def _get_builtin_indexes() -> dict:
    """Read built-in action and integration index JSON files from disk.

    Returns a dict with keys 'builtin_actions' and 'builtin_integrations'.
    Each value is the grouped dict from the corresponding JSON file,
    or an empty dict if the file is missing or invalid.
    """
    builtin = {}
    for key, path in [
        ("builtin_actions", ACTIONS_DIR / "action_index.json"),
        ("builtin_integrations", ACTIONS_DIR / "integrations" / "integration_index.json"),
    ]:
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
            builtin[key] = data if isinstance(data, dict) else {}
        else:
            builtin[key] = {}
    return builtin


def build_builtin_indexes() -> None:
    """Regenerate built-in action and integration indexes. For framework developers only."""
    _build_func_index_from_dir(ACTIONS_DIR, "actions", "action_index.json")
    _build_func_index_from_dir(ACTIONS_DIR / "integrations", "actions.integrations", "integration_index.json")


def _ensure_musicsheets_path(project_root: Path) -> None:
    musicsheets_path = str(project_root / "musicsheets")
    if musicsheets_path not in sys.path:
        sys.path.insert(0, musicsheets_path)


def build_local_action_index(project_root: Path) -> dict:
    """Scan local action files and rebuild the local action_index.json. Returns grouped dict."""
    _ensure_musicsheets_path(project_root)
    return _build_func_index_from_dir(
        project_root / "musicsheets" / "local_actions",
        "local_actions",
        "action_index.json",
    )


def build_local_integration_index(project_root: Path) -> dict:
    """Scan local integration files and rebuild the local integration_index.json. Returns grouped dict."""
    _ensure_musicsheets_path(project_root)
    return _build_func_index_from_dir(
        project_root / "musicsheets" / "local_actions" / "local_integrations",
        "local_actions.local_integrations",
        "integration_index.json",
    )


def get_action_indexes(project_root: Path) -> dict:
    """Merge built-in and local action indexes. Reads built-in from disk, rebuilds local."""
    builtin = _get_builtin_indexes()
    actions = dict(builtin["builtin_actions"])
    actions.update(build_local_action_index(project_root))
    return actions


def get_integration_indexes(project_root: Path) -> dict:
    """Merge built-in and local integration indexes. Reads built-in from disk, rebuilds local."""
    builtin = _get_builtin_indexes()
    integrations = dict(builtin["builtin_integrations"])
    integrations.update(build_local_integration_index(project_root))
    return integrations