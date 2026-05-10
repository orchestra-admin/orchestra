import json
import sys
from pathlib import Path

from conductor_agent.conductor_tasks.config import ACTIONS_DIR, get_project_root, get_project_config_path
from conductor_agent.conductor_tasks.secrets import get_secret, set_secret


def _read_index_silent(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return json.load(f)


def push_secrets() -> None:
    project_root = get_project_root()
    config_path = get_project_config_path(project_root)

    backend = "aws_ssm"
    dotenv_path = ".env"
    if config_path.exists():
        with open(config_path, "r") as f:
            data = json.load(f)
        secrets_cfg = data.get("secrets", {})
        backend = secrets_cfg.get("backend", "aws_ssm")
        dotenv_path = secrets_cfg.get("backend_configs", {}).get("env", {}).get("path", ".env")

    if backend == "env":
        print("[*] Already using env backend — nothing to push.")
        return

    env_file = project_root / dotenv_path
    if not env_file.exists():
        print(f"[!] .env file not found at {env_file}. Nothing to push.")
        return

    lines = env_file.read_text().splitlines(keepends=True)
    entries = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if not key or not value or value.startswith("<set_in_"):
            continue
        entries[key] = value

    if not entries:
        print("[*] No real values found in .env — nothing to push.")
        return

    pushed = 0
    placeholder = f"<set_in_{backend}>"
    for key, value in entries.items():
        try:
            set_secret(key, value)
            pushed += 1
            print(f"[+] Pushed {key} to {backend}")
        except Exception as exc:
            print(f"[!] Failed to push {key}: {exc}", file=sys.stderr)
            continue

    if pushed > 0:
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.partition("=")[0].strip()
                if k in entries:
                    new_lines.append(f"{k}={placeholder}\n")
                    continue
            new_lines.append(line)
        env_file.write_text("".join(new_lines))
        print(f"[*] .env values replaced with {placeholder}")

    print(f"[+] Pushed {pushed} key(s) to {backend} backend")


def list_secrets() -> None:
    project_root = get_project_root()

    index_paths = [
        ACTIONS_DIR / "integrations" / "integration_index.json",
        project_root / "musicsheets" / "local_actions" / "local_integrations" / "integration_index.json",
    ]

    all_secrets = set()
    for idx_path in index_paths:
        for entry in _read_index_silent(idx_path):
            for key in entry.get("secrets", []):
                all_secrets.add(key)

    if not all_secrets:
        print("(No integrations found)")
        return

    for key in sorted(all_secrets):
        try:
            get_secret(key)
            print(f"  [set] {key}")
        except Exception:
            print(f"  [  ] {key}")
