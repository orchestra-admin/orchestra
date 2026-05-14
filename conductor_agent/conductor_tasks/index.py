import importlib
import inspect
import json
import re
import sys
from pathlib import Path

from conductor_agent.conductor_tasks.config import ACTIONS_DIR, get_project_root

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
            print(f"Warning: Could not import {module_name}: {e}")
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
    return _build_index_for_directory(
        directory=ACTIONS_DIR,
        module_prefix="actions",
        output_json_name="actions_index.json"
    )


def build_local_action_index(project_root: Path):
    musicsheets_path = str(project_root / "musicsheets")
    if musicsheets_path not in sys.path:
        sys.path.insert(0, musicsheets_path)
        
    return _build_index_for_directory(
        directory=project_root / "musicsheets" / "local_actions",
        module_prefix="local_actions",
        output_json_name="action_index.json"
    )


def _build_integration_index_grouped(directory: Path, module_prefix: str, output_json_name: str) -> dict:
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
    result = _build_integration_index_grouped(
        directory=ACTIONS_DIR / "integrations",
        module_prefix="actions.integrations",
        output_json_name="integration_index.json"
    )
    sync_env_keys(result)
    return result


def build_local_integration_index(project_root: Path):
    musicsheets_path = str(project_root / "musicsheets")
    if musicsheets_path not in sys.path:
        sys.path.insert(0, musicsheets_path)

    result = _build_integration_index_grouped(
        directory=project_root / "musicsheets" / "local_actions" / "local_integrations",
        module_prefix="local_actions.local_integrations",
        output_json_name="integration_index.json"
    )
    sync_env_keys(result)
    return result


def _print_index(title: str, items: list | dict) -> None:
    print(f"\n--- {title} ---\n")

    if isinstance(items, dict):
        if not items:
            print("  (None found)")
            return
        for mod, info in items.items():
            print(f"[{mod}]")
            for func in info["functions"]:
                desc = func.get("description", "")
                if desc:
                    print(f"  - {func['function']}(): {desc}")
                else:
                    print(f"  - {func['function']}()")
            print()
        return

    grouped = {}
    for item in items:
        mod = item["module"]
        grouped.setdefault(mod, []).append(item)

    if not grouped:
        print("  (None found)")
        return

    for mod, funcs in grouped.items():
        print(f"[{mod}]")
        for func in funcs:
            desc = func.get("description", "")
            if desc:
                print(f"  - {func['function']}(): {desc}")
            else:
                print(f"  - {func['function']}()")
        print()


def sync_env_keys(integrations: dict) -> None:
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
        print(f"[*] Added {len(missing)} new secret key label(s) to .env: {', '.join(missing)}")


def print_actions():
    actions_list = build_action_index()
    project_root = get_project_root()
    actions_list.extend(build_local_action_index(project_root))
    _print_index("Available Orchestra Actions", actions_list)


def print_integrations():
    integrations = build_integration_index()
    project_root = get_project_root()
    integrations.update(build_local_integration_index(project_root))
    _print_index("Available Orchestra Integrations", integrations)
