import re
import sys
from pathlib import Path

from composer_agent.composer_tasks.composer_helpers import (
    MAX_RETRIES,
    _format_actions,
    _read_index,
    _read_integration_index,
    _strip_markdown_fences,
    _validate_python,
    _write_action,
)
from conductor_agent.conductor_tasks.config import ACTIONS_DIR, get_project_root
from conductor_agent.conductor_tasks.index import build_integration_index, build_local_integration_index
from conductor_agent.conductor_tasks.llm import llm_query

NAME_PATTERN = re.compile(r"^\#\s*(\w[\w_]*)\.py")


def _parse_name(code: str) -> str | None:
    m = NAME_PATTERN.match(code.strip())
    if m:
        return m.group(1) + ".py"
    return None


def _strip_name_line(code: str) -> str:
    return NAME_PATTERN.sub("", code.strip(), count=1).strip() + "\n"


def compose_integration(description: str, name: str | None = None) -> None:
    project_root = get_project_root()
    local_integrations_dir = project_root / "musicsheets" / "local_actions" / "local_integrations"

    if not local_integrations_dir.parent.exists():
        print(
            "Error: local_actions/ not found. "
            "Run this command from an initialized Orchestra project.",
            file=sys.stderr,
        )
        sys.exit(1)

    prompt_path = Path(__file__).parent / "compose_integration.md"
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    builtin_integrations = _read_integration_index(ACTIONS_DIR / "integrations" / "integration_index.json")
    local_integrations = _read_integration_index(project_root / "musicsheets" / "local_actions" / "local_integrations" / "integration_index.json")

    reference_example = ""
    reference_path = ACTIONS_DIR / "integrations" / "slack_integration.py"
    if reference_path.exists():
        reference_example = reference_path.read_text().strip()

    integration_summary = _format_actions({**builtin_integrations, **local_integrations})

    local_files = sorted(p.name for p in local_integrations_dir.glob("*.py") if p.name != "__init__.py")
    files_context = "\n".join(f"- {f}" for f in local_files) if local_files else "(None)"

    all_secrets = set()
    for info in {**builtin_integrations, **local_integrations}.values():
        for key in info.get("secrets", []):
            all_secrets.add(key)

    secrets_context = ""
    if all_secrets:
        secrets_context = "\n".join(f"- {k}" for k in sorted(all_secrets))

    print(f"[*] Generating integration: {description}")

    retry_prompt = (
        "The previous response contained invalid Python code. "
        "Please output ONLY valid Python with no markdown fences or extra text.\n\n"
    )

    user_message = (
        "## Reference Example\n\n"
        f"```python\n{reference_example or '(No reference available)'}\n```\n\n"
        "## Existing Integrations (do not duplicate)\n\n"
        f"{integration_summary}\n\n"
        "## Local Integration Files (do not recreate)\n\n"
        f"{files_context}\n\n"
        "## Available Secret Key Names (use with get_secret() only)\n\n"
        f"{secrets_context or '(None)'}\n\n"
        "## Request\n\n"
        f"Generate an integration module for: {description}"
    )

    code = None
    for attempt in range(1, MAX_RETRIES + 1):
        code = llm_query(system_prompt, user_message)
        code = _strip_markdown_fences(code)

        error = _validate_python(code, "integration")
        if error is None:
            break

        if attempt < MAX_RETRIES:
            print(
                f"[!] Attempt {attempt}/{MAX_RETRIES}: {error}. Retrying...",
                file=sys.stderr,
            )
            user_message = retry_prompt + f"Error: {error}\n\n" + user_message
        else:
            print(
                f"[!] Attempt {attempt}/{MAX_RETRIES}: {error}. "
                "Writing output anyway (file may need manual fixes).",
                file=sys.stderr,
            )

    if code.strip().startswith("# SKIP"):
        print(f"[*] {code.strip().splitlines()[0]}")
        return

    filename = name or _parse_name(code)
    if not filename:
        print(
            "Error: integration output must include a # filename.py comment on the first line, or use --name.",
            file=sys.stderr,
        )
        sys.exit(1)

    code = _strip_name_line(code)

    _write_action(local_integrations_dir, filename, code)
    print(f"[+] Integration written to local_actions/local_integrations/{filename}")

    build_integration_index()
    build_local_integration_index(project_root)
