import logging
import re
from pathlib import Path

from composer_agent.composer_tasks.composer_helpers import (
    COMPOSE_RESULT,
    MAX_RETRIES,
    _format_actions,
    _read_integration_index,
    _strip_markdown_fences,
    _validate_python,
    _write_action,
)
from orchestra_core.config import ACTIONS_DIR, get_project_root
from orchestra_core.index import build_action_index, build_integration_index
from orchestra_core.llm import llm_query
from orchestra_core.secrets import sync_env_keys

logger = logging.getLogger(__name__)

NAME_PATTERN = re.compile(r"^\#\s*(\w[\w_]*)\.py")


def _parse_name(code: str) -> str | None:
    m = NAME_PATTERN.match(code.strip())
    if m:
        return m.group(1) + ".py"
    return None


def _strip_name_line(code: str) -> str:
    return NAME_PATTERN.sub("", code.strip(), count=1).strip() + "\n"


def compose_integration(description: str, name: str | None = None) -> COMPOSE_RESULT:
    """Generate an integration Python module from a natural language description."""
    project_root = get_project_root()
    local_integrations_dir = (
        project_root / "musicsheets" / "local_actions" / "local_integrations"
    )

    if not local_integrations_dir.parent.exists():
        return (
            False,
            None,
            "local_actions/ not found. Run this from an initialized Orchestra project.",
            [],
        )

    build_action_index(project_root)
    build_integration_index(project_root)

    prompt_path = Path(__file__).parent / "compose_integration.md"
    with open(prompt_path) as f:
        system_prompt = f.read()

    builtin_integrations = _read_integration_index(
        project_root
        / "musicsheets"
        / "local_actions"
        / "local_integrations"
        / "builtin_integration_index.json"
    )
    local_integrations = _read_integration_index(
        project_root
        / "musicsheets"
        / "local_actions"
        / "local_integrations"
        / "local_integration_index.json"
    )

    reference_example = ""
    reference_path = ACTIONS_DIR / "integrations" / "slack_integration.py"
    if reference_path.exists():
        reference_example = reference_path.read_text().strip()

    integration_summary = _format_actions(
        {**builtin_integrations, **local_integrations}
    )

    local_files = sorted(
        p.name for p in local_integrations_dir.glob("*.py") if p.name != "__init__.py"
    )
    files_context = (
        "\n".join(f"- {f}" for f in local_files) if local_files else "(None)"
    )

    all_secrets = set()
    for info in {**builtin_integrations, **local_integrations}.values():
        for key in info.get("secrets", []):
            all_secrets.add(key)

    secrets_context = ""
    if all_secrets:
        secrets_context = "\n".join(f"- {k}" for k in sorted(all_secrets))

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
    validation_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        code = llm_query(system_prompt, user_message)
        code = _strip_markdown_fences(code)

        validation_error = _validate_python(code, "integration")
        if validation_error is None:
            break

        logger.warning(
            "compose.llm.retry",
            extra={
                "data": {
                    "attempt": attempt,
                    "max_retries": MAX_RETRIES,
                    "error": validation_error,
                }
            },
        )
        if attempt < MAX_RETRIES:
            user_message = (
                retry_prompt + f"Error: {validation_error}\n\n" + user_message
            )

    if validation_error is not None:
        logger.error(
            "compose.llm.failed_validation", extra={"data": {"error": validation_error}}
        )
        return (
            False,
            None,
            (
                f"Generated code failed validation after {MAX_RETRIES} "
                f"attempts: {validation_error}"
            ),
            [],
        )

    if code.strip().startswith("# SKIP"):
        skip_msg = code.strip().splitlines()[0]
        return (True, None, skip_msg, [])

    filename = name or _parse_name(code)
    if not filename:
        return (
            False,
            None,
            (
                "Integration output must include a # filename.py "
                "comment on the first line, or use --name."
            ),
            [],
        )

    code = _strip_name_line(code)

    try:
        _write_action(local_integrations_dir, filename, code)
    except ValueError as e:
        return (False, None, str(e), [])

    integrations = build_integration_index(project_root)
    new_keys = sync_env_keys(integrations)

    return (True, str(local_integrations_dir / filename), None, new_keys)
