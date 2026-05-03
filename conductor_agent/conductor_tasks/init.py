import secrets
import shutil
import subprocess
from pathlib import Path

from conductor_agent.conductor_tasks.config import INIT_ASSETS_DIR, get_project_root


def _is_docker_installed() -> bool:
    try:
        subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def init_project() -> None:
    project_root = get_project_root()

    shutil.copytree(INIT_ASSETS_DIR, project_root, dirs_exist_ok=True)

    env_example = project_root / ".env.example"
    env_file = project_root / ".env"

    if env_example.exists() and not env_file.exists():
        content = env_example.read_text()
        content = content.replace("WEBHOOK_SECRET=\n", f"WEBHOOK_SECRET={secrets.token_hex(32)}\n", 1)
        env_file.write_text(content)

    print()
    print("  ▗▄▖ ▗▄▄▖  ▗▄▄▖▗▖ ▗▖▗▄▄▄▖ ▗▄▄▖▗▄▄▄▖▗▄▄▖  ▗▄▖ ")
    print(" ▐▌ ▐▌▐▌ ▐▌▐▌   ▐▌ ▐▌▐▌   ▐▌     █  ▐▌ ▐▌▐▌ ▐▌")
    print(" ▐▌ ▐▌▐▛▀▚▖▐▌   ▐▛▀▜▌▐▛▀▀▘ ▝▀▚▖  █  ▐▛▀▚▖▐▛▀▜▌")
    print(" ▝▚▄▞▘▐▌ ▐▌▝▚▄▄▖▐▌ ▐▌▐▙▄▄▖▗▄▄▞▘  █  ▐▌ ▐▌▐▌ ▐▌")
    print()
    print()
    print("  𝄞♫♪ Welcome to Orchestra! 𝄞♫♪")
    print()

    print(f"[+] Initialized Orchestra project at {project_root}")

    print("[*] Next steps:")
    print("  - Fill in .env with your real secrets.")
    print("  - Review .local_config/orchestra.json and adjust Redis settings if needed.")
    print("  - Run orchestra compose <playbook.md> from this directory.")

    if not _is_docker_installed():
        print("\n[!] Docker is not installed. Orchestra requires Docker to run the built-in Automation Engine.")
        print("    Install Docker Desktop: https://docs.docker.com/get-started/")
        print("    Then run: docker compose up -d")
    else:
        print("\n    Start your Orchestra stack: docker compose up -d")
