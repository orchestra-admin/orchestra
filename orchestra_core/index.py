import importlib
import inspect
import json
import re
import sys
from pathlib import Path
import logging

from orchestra_core.config import ACTIONS_DIR, get_project_root

logger = logging.getLogger(__name__)

GET_SECRET_PATTERN = re.compile(r'get_secret\("([^"]+)"\)')


def _extract_secret_keys(filepath: Path) -> list[str]:
    keys = set()
    try:
        with open(filepath, "r") as f:
            source = f.read()
        for key in GET_SECRET_PATTERN.findall(source):
            keys.add(key)
    except Exception:
        pass
    return sorted(keys)


def _build_index_for_directory(directory: Path, module_prefix: str, output_json_name: str) -> list:
    signatures = []
    
    if not directory.exists():
        return []
        
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
        
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("_") and getattr(obj, "__module__", "") == module.__name__:
                sig = str(inspect.signature(obj))
                doc = inspect.getdoc(obj)
                
                description = ""
                if doc:
                    description = doc.strip().split('\n\n')[0].replace('\n', ' ').strip()
                
                signatures.append({
                    "module": module_name,
                    "function": name,
                    "signature": sig,
                    "description": description,
                    "secrets": secret_keys,
                })
                
    index_path = directory / output_json_name
    with open(index_path, "w") as f:
        json.dump(signatures, f, indent=4)
        
    return signatures


def build_action_index():
    """Build the built-in action index from actions/*.py, writing action_index.json."""
    return _build_index_for_directory(
        directory=ACTIONS_DIR,
        module_prefix="actions",
        output_json_name="action_index.json"
    )


def build_local_action_index(project_root: Path):
    """Build the local action index from musicsheets/local_actions/*.py."""
    musicsheets_path = str(project_root / "musicsheets")
    if musicsheets_path not in sys.path:
        sys.path.insert(0, musicsheets_path)
        
    return _build_index_for_directory(
        directory=project_root / "musicsheets" / "local_actions",
        module_prefix="local_actions",
        output_json_name="action_index.json"
    )


def _build_integration_index_grouped(directory: Path, module_prefix: str, output_json_name: str) -> dict:
    if not directory.exists():
        return {}
    flat = _build_index_for_directory(directory, module_prefix, output_json_name)
    grouped = {}
    for entry in flat:
        mod = entry["module"]
        if mod not in grouped:
            grouped[mod] = {"secrets": entry.get("secrets", []), "functions": []}
        grouped[mod]["functions"].append({
            "function": entry["function"],
            "signature": entry.get("signature", ""),
            "description": entry.get("description", ""),
        })
    index_path = directory / output_json_name
    with open(index_path, "w") as f:
        json.dump(grouped, f, indent=4)
    return grouped


def build_integration_index():
    """Build the built-in integration index, grouped by module."""
    return _build_integration_index_grouped(
        directory=ACTIONS_DIR / "integrations",
        module_prefix="actions.integrations",
        output_json_name="integration_index.json"
    )


def build_local_integration_index(project_root: Path):
    """Build the local integration index from musicsheets/local_actions/local_integrations/."""
    musicsheets_path = str(project_root / "musicsheets")
    if musicsheets_path not in sys.path:
        sys.path.insert(0, musicsheets_path)

    return _build_integration_index_grouped(
        directory=project_root / "musicsheets" / "local_actions" / "local_integrations",
        module_prefix="local_actions.local_integrations",
        output_json_name="integration_index.json"
    )


def sync_env_keys(integrations: dict) -> None:
    """Append missing secret key labels from the integration index to .env."""
    all_secrets = set()
    for info in integrations.values():
        for key in info.get("secrets", []):
            all_secrets.add(key)

    if not all_secrets:
        return

    project_root = get_project_root()
    env_file = project_root / ".env"
    existing_lines = env_file.read_text().splitlines() if env_file.exists() else []
    existing_keys = set()
    for line in existing_lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            existing_keys.add(line.split("=", 1)[0].strip())

    missing = sorted(all_secrets - existing_keys)
    if missing:
        with open(env_file, "a") as f:
            if existing_lines and existing_lines[-1].strip() != "":
                f.write("\n")
            for key in missing:
                f.write(f"{key}=\n")
        logger.info("admin.env.synced", extra={"data": {"added": len(missing), "keys": sorted(missing)}})


def get_actions_index():
    actions_list = build_action_index()
    project_root = get_project_root()
    actions_list.extend(build_local_action_index(project_root))
    return actions_list


def get_integrations_index():
    integrations = build_integration_index()
    project_root = get_project_root()
    integrations.update(build_local_integration_index(project_root))
    return integrations
