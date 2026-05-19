import re
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
from orchestra_core.config import ACTIONS_DIR, get_project_root
from orchestra_core.index import get_actions_index
from orchestra_core.llm import llm_query

NAME_PATTERN = re.compile(r"^\#\s*(\w[\w_]*)\.py")


def _parse_name(code: str) -> str | None:
    m = NAME_PATTERN.match(code.strip())
    if m:
        return m.group(1) + ".py"
    return None


def _strip_name_line(code: str) -> str:
    return NAME_PATTERN.sub("", code.strip(), count=1).strip() + "\n"


def compose_action(description: str, name: str | None = None) -> tuple[bool, str | None, str | None]:
    """Generate an action Python module from a natural language description."""
    project_root = get_project_root()
    local_actions_dir = project_root / "musicsheets" / "local_actions"

    if not local_actions_dir.exists():
        return (False, None, "local_actions/ not found. Run this command from an initialized Orchestra project.", None)

    prompt_path = Path(__file__).parent / "compose_action.md"
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    builtin_integrations = _read_integration_index(ACTIONS_DIR / "integrations" / "integration_index.json")
    local_action_index = _read_index(project_root / "musicsheets" / "local_actions" / "action_index.json")
    local_integrations = _read_integration_index(project_root / "musicsheets" / "local_actions" / "local_integrations" / "integration_index.json")

    reference_example = ""
    reference_path = ACTIONS_DIR / "slack.py"
    if reference_path.exists():
        reference_example = reference_path.read_text().strip()

    integration_summary = _format_actions({**builtin_integrations, **local_integrations})

    all_secrets = set()
    for info in {**builtin_integrations, **local_integrations}.values():
        for key in info.get("secrets", []):
            all_secrets.add(key)

    secrets_context = ""
    if all_secrets:
        secrets_context = "\n".join(f"- {k}" for k in sorted(all_secrets))

    existing_files_context = "(No existing local actions)"
    local_files = sorted(p for p in local_actions_dir.glob("*.py") if p.name != "__init__.py")
    if local_files:
        lines = []
        for lf in local_files:
            mod_key = f"local_actions.{lf.stem}"
            info = local_action_index.get(mod_key)
            if info:
                func_desc = []
                for func in info["functions"]:
                    func_desc.append(f"  {func['function']}({func.get('signature', '')})")
                if func_desc:
                    lines.append(f"{lf.name}:")
                    lines.extend(func_desc)
        if lines:
            existing_files_context = "\n".join(lines)

    local_files_context = "\n".join(f"- {f}" for f in (p.name for p in local_files)) if local_files else "(None)"

    retry_prompt = (
        "The previous response contained invalid Python code. "
        "Please output ONLY valid Python with no markdown fences or extra text.\n\n"
    )

    user_message = (
        "## Reference Example\n\n"
        f"```python\n{reference_example or '(No reference available)'}\n```\n\n"
        "## Available Integrations (for API/credential access)\n\n"
        f"{integration_summary}\n\n"
        "## Available Secret Key Names (use via integrations, not directly)\n\n"
        f"{secrets_context or '(None)'}\n\n"
        "## Local Action Files (do not recreate)\n\n"
        f"{local_files_context}\n\n"
        "## Existing Local Action Files (append to matching file if related)\n\n"
        f"{existing_files_context}\n\n"
        "## Request\n\n"
        f"Generate an action function for: {description}"
    )

    code = None
    for attempt in range(1, MAX_RETRIES + 1):
        code = llm_query(system_prompt, user_message)
        code = _strip_markdown_fences(code)

        error = _validate_python(code, "action")
        if error is None:
            break

        if attempt < MAX_RETRIES:
            user_message = retry_prompt + f"Error: {error}\n\n" + user_message
        else:
            pass

    if code.strip().startswith("# SKIP"):
        skip_msg = code.strip().splitlines()[0]
        return (True, None, skip_msg, None)

    filename = name or _parse_name(code)
    if not filename:
        return (False, None, "Action output must include a # filename.py comment on the first line, or use --name.", None)

    code = _strip_name_line(code)

    try:
        _write_action(local_actions_dir, filename, code)
    except ValueError as e:
        return (False, None, str(e), None)

    get_actions_index(project_root)

    return (True, str(local_actions_dir / filename), None, None)
