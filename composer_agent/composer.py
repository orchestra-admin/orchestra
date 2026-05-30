import logging
import re
from pathlib import Path

from composer_agent.composer_tasks.compose_action import (
    compose_action as _compose_action,
)
from composer_agent.composer_tasks.compose_integration import (
    compose_integration as _compose_integration,
)
from composer_agent.composer_tasks.composer_helpers import (
    COMPOSE_RESULT,
    MAX_RETRIES,
    _format_actions,
    _read_index,
    _read_integration_index,
    _strip_markdown_fences,
    _validate_python,
    _write_action,
)
from orchestra_core.config import get_project_root
from orchestra_core.index import build_action_index, build_integration_index
from orchestra_core.llm import llm_query
from orchestra_core.secrets import sync_env_keys

logger = logging.getLogger(__name__)

ACTIONS_MARKER = re.compile(r"###ACTIONS (.+?)###(.*?)###END ACTIONS###", re.DOTALL)
SCRIPT_SPLIT = re.compile(r"###SCRIPT###", re.DOTALL)


def _parse_output(raw: str) -> tuple[dict[str, str], str]:
    parts = SCRIPT_SPLIT.split(raw, 1)
    before_script = parts[0] if parts else ""
    script = parts[1].strip() if len(parts) > 1 else ""

    if not script:
        return ({}, raw.strip())

    actions = {}
    for match in ACTIONS_MARKER.finditer(before_script):
        filename = match.group(1).strip()
        code = match.group(2).strip()
        if filename and code:
            actions[filename] = code

    return (actions, script)


def compose_playbook(
    playbook_path: str | Path, output_path: str | Path | None = None
) -> COMPOSE_RESULT:
    """Convert a playbook markdown file into an executable musicsheet script."""
    project_root = get_project_root()
    playbook_path = Path(playbook_path)
    musicsheets_dir = project_root / "musicsheets"

    if not musicsheets_dir.is_dir():
        return (
            False,
            None,
            "musicsheets/ not found. Run this command from an initialized Orchestra project.",
            [],
        )

    build_action_index(project_root)
    build_integration_index(project_root)

    if not output_path:
        output_path = musicsheets_dir / f"{playbook_path.stem}.py"
    else:
        output_path = Path(output_path)

    with open(playbook_path) as f:
        playbook_text = f.read()

    prompt_path = Path(__file__).parent / "composer.md"
    with open(prompt_path) as f:
        system_prompt = f.read()

    builtin_actions = _read_index(
        project_root / "musicsheets" / "local_actions" / "builtin_action_index.json"
    )
    builtin_integrations = _read_integration_index(
        project_root
        / "musicsheets"
        / "local_actions"
        / "local_integrations"
        / "builtin_integration_index.json"
    )
    local_actions = _read_index(
        project_root / "musicsheets" / "local_actions" / "local_action_index.json"
    )
    local_integrations = _read_integration_index(
        project_root
        / "musicsheets"
        / "local_actions"
        / "local_integrations"
        / "local_integration_index.json"
    )

    actions_summary = _format_actions({**builtin_actions, **local_actions})

    all_secrets = set()
    for info in {**builtin_integrations, **local_integrations}.values():
        for key in info.get("secrets", []):
            all_secrets.add(key)

    secrets_context = ""
    if all_secrets:
        secrets_context = "\n".join(f"- {k}" for k in sorted(all_secrets))

    retry_prompt = (
        "The previous response contained invalid Python code. "
        "Please output valid Python using the required markers with no markdown fences or extra text.\n\n"
    )

    user_message = (
        "## Available Actions\n\n"
        f"{actions_summary}\n\n"
        "## Available Secret Key Names (use with get_secret() only)\n\n"
        f"{secrets_context or '(None)'}\n\n"
        "## Playbook to Convert\n\n"
        f"{playbook_text}\n\n"
        "Generate the Python script now."
    )

    local_actions_dir = project_root / "musicsheets" / "local_actions"

    validation_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        raw_output = llm_query(system_prompt, user_message)
        raw_output = _strip_markdown_fences(raw_output)

        actions, script = _parse_output(raw_output)

        validation_error = None
        for filename, action_code in actions.items():
            validation_error = _validate_python(
                action_code, f"local_actions/{filename}"
            )
            if validation_error:
                break
        if validation_error is None:
            validation_error = _validate_python(script, str(output_path.name))

        if validation_error is None:
            for filename, action_code in actions.items():
                try:
                    _write_action(local_actions_dir, filename, action_code)
                except ValueError as e:
                    return (False, None, str(e), [])
            with open(output_path, "w") as f:
                f.write(script)
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
            "compose.llm.failed_validation",
            extra={
                "data": {"error": validation_error, "output_path": str(output_path)}
            },
        )
        draft_path = output_path.with_suffix(".draft.py")
        with open(draft_path, "w") as f:
            f.write(script)
        return (
            False,
            None,
            f"Generated code failed validation after {MAX_RETRIES} attempts: {validation_error}. Draft written to {draft_path}",
            [],
        )

    build_action_index(project_root)
    integrations = build_integration_index(project_root)
    new_keys = sync_env_keys(integrations)

    return (True, str(output_path), None, new_keys)


def compose(target: str, **kwargs) -> COMPOSE_RESULT:
    """Route compose commands to the appropriate target (playbook, action, or integration)."""
    if target == "playbook":
        return compose_playbook(kwargs["playbook"])
    elif target == "action":
        return _compose_action(kwargs["description"], kwargs.get("name"))
    elif target == "integration":
        return _compose_integration(kwargs["description"], kwargs.get("name"))
    else:
        return (False, None, f"Unknown compose target '{target}'.", [])
