import re
from pathlib import Path

from composer_agent.composer_tasks.compose_action import compose_action as _compose_action
from composer_agent.composer_tasks.compose_integration import compose_integration as _compose_integration
from composer_agent.composer_tasks.composer_helpers import (
    MAX_RETRIES,
    _format_actions,
    _read_index,
    _read_integration_index,
    _strip_markdown_fences,
    _validate_python,
    _write_action,
)
from orchestra_core.llm import llm_query
from orchestra_core.config import ACTIONS_DIR, get_project_root
from orchestra_core.index import build_action_index, build_integration_index
from orchestra_core.secrets import sync_env_keys

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


def compose_playbook(playbook_path, output_path=None) -> tuple[bool, str | None, str | None]:
    """Convert a playbook markdown file into an executable musicsheet script."""
    project_root = get_project_root()
    playbook_path = Path(playbook_path)
    musicsheets_dir = project_root / "musicsheets"

    if not musicsheets_dir.is_dir():
        return (False, None, "musicsheets/ not found. Run this command from an initialized Orchestra project.")

    build_action_index(project_root)
    build_integration_index(project_root)

    if not output_path:
        output_path = musicsheets_dir / f"{playbook_path.stem}.py"
    else:
        output_path = Path(output_path)

    with open(playbook_path, "r") as f:
        playbook_text = f.read()

    prompt_path = Path(__file__).parent / "composer.md"
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    builtin_actions = _read_index(project_root / "musicsheets" / "local_actions" / "builtin_action_index.json")
    builtin_integrations = _read_integration_index(project_root / "musicsheets" / "local_actions" / "local_integrations" / "builtin_integration_index.json")
    local_actions = _read_index(project_root / "musicsheets" / "local_actions" / "local_action_index.json")
    local_integrations = _read_integration_index(project_root / "musicsheets" / "local_actions" / "local_integrations" / "local_integration_index.json")

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

    for attempt in range(1, MAX_RETRIES + 1):
        raw_output = llm_query(system_prompt, user_message)
        raw_output = _strip_markdown_fences(raw_output)

        actions, script = _parse_output(raw_output)

        validation_error = None
        for filename, action_code in actions.items():
            validation_error = _validate_python(action_code, f"local_actions/{filename}")
            if validation_error:
                break
        if validation_error is None:
            validation_error = _validate_python(script, str(output_path.name))

        if validation_error is None:
            for filename, action_code in actions.items():
                try:
                    _write_action(local_actions_dir, filename, action_code)
                except ValueError as e:
                    return (False, None, str(e), None)
            with open(output_path, "w") as f:
                f.write(script)
            break

        if attempt < MAX_RETRIES:
            user_message = retry_prompt + f"Error: {validation_error}\n\n" + user_message
        else:
            with open(output_path, "w") as f:
                f.write(script)

    build_action_index(project_root)
    integrations = build_integration_index(project_root)
    new_keys = sync_env_keys(integrations)

    return (True, str(output_path), None, new_keys)


def compose(target: str, **kwargs) -> tuple[bool, str | None, str | None, list[str]]:
    """Route compose commands to the appropriate target (playbook, action, or integration)."""
    if target == "playbook":
        return compose_playbook(kwargs["playbook"])
    elif target == "action":
        return _compose_action(kwargs["description"], kwargs.get("name"))
    elif target == "integration":
        return _compose_integration(kwargs["description"], kwargs.get("name"))
    else:
        return (False, None, f"Unknown compose target '{target}'.", None)
