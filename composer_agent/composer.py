import json
import re
import sys
from pathlib import Path

from conductor_agent.conductor_tasks.llm import llm_query
from conductor_agent.conductor_tasks.config import ACTIONS_DIR, get_project_root
from conductor_agent.conductor_tasks.index import (
    build_action_index,
    build_integration_index,
    build_local_action_index,
    build_local_integration_index,
)

MAX_RETRIES = 3

ACTIONS_MARKER = re.compile(r"###ACTIONS (.+?)###(.*?)###END ACTIONS###", re.DOTALL)
SCRIPT_SPLIT = re.compile(r"###SCRIPT###", re.DOTALL)


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*\n?", "", text, count=1)
        lines = text.rsplit("\n")
        if lines and lines[-1].strip() == "```":
            text = "\n".join(lines[:-1])
        elif text.rstrip().endswith("```"):
            text = re.sub(r"\n?```\s*$", "", text, count=1)

    return text.strip() + "\n"


def _validate_python(code: str, label: str = "<composer_output>") -> str | None:
    try:
        compile(code, label, "exec")
    except SyntaxError as exc:
        return f"SyntaxError in {label} line {exc.lineno}: {exc.msg}"
    return None


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


def _write_action(base_dir: Path, relative_path: str, code: str) -> None:
    target = base_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    code = code.strip() + "\n"

    if target.exists():
        existing = target.read_text().rstrip()
        combined = existing + "\n\n" + code
    else:
        combined = code

    target.write_text(combined)


def _read_index(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return json.load(f)


def _format_actions(entries: list) -> str:
    if not entries:
        return "(None)"
    lines = []
    for entry in entries:
        mod = entry.get("module", "")
        func = entry.get("function", "")
        sig = entry.get("signature", "")
        desc = entry.get("description", "")
        lines.append(f"- {mod}.{func}{sig}: {desc}")
    return "\n".join(lines)


def _slugify(description: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", description.lower()).strip("_")
    words = [w for w in stem.split("_") if w and len(w) > 2]
    return "_".join(words[:4])


def compose_script(playbook_path, output_path=None):
    project_root = get_project_root()
    playbook_path = Path(playbook_path)
    musicsheets_dir = project_root / "musicsheets"

    if not musicsheets_dir.is_dir():
        print(
            "Error: musicsheets/ not found in current directory. "
            "Run this command from an initialized Orchestra project.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not output_path:
        output_path = musicsheets_dir / f"{playbook_path.stem}.py"
    else:
        output_path = Path(output_path)

    with open(playbook_path, "r") as f:
        playbook_text = f.read()

    prompt_path = Path(__file__).parent / "composer.md"
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    builtin_actions = _read_index(ACTIONS_DIR / "actions_index.json")
    builtin_integrations = _read_index(ACTIONS_DIR / "integrations" / "integration_index.json")
    local_actions = _read_index(project_root / "musicsheets" / "local_actions" / "action_index.json")
    local_integrations = _read_index(project_root / "musicsheets" / "local_actions" / "local_integrations" / "integration_index.json")

    actions_summary = _format_actions(builtin_actions + local_actions)

    all_secrets = set()
    for entry in builtin_integrations + local_integrations:
        for key in entry.get("secrets", []):
            all_secrets.add(key)

    secrets_context = ""
    if all_secrets:
        secrets_context = "\n".join(f"- {k}" for k in sorted(all_secrets))

    print(f"[*] Composing script for {playbook_path}...")

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
                _write_action(local_actions_dir, filename, action_code)
                print(f"[+] Action written to local_actions/{filename}")
            with open(output_path, "w") as f:
                f.write(script)
            break

        if attempt < MAX_RETRIES:
            print(
                f"[!] Attempt {attempt}/{MAX_RETRIES}: {validation_error}. Retrying...",
                file=sys.stderr,
            )
            user_message = retry_prompt + f"Error: {validation_error}\n\n" + user_message
        else:
            print(
                f"[!] Attempt {attempt}/{MAX_RETRIES}: {validation_error}. "
                "Writing output anyway (script may need manual fixes).",
                file=sys.stderr,
            )
            with open(output_path, "w") as f:
                f.write(script)

    print(f"[+] Output written to {output_path}")

    build_action_index()
    build_integration_index()
    build_local_action_index(project_root)
    build_local_integration_index(project_root)


def compose_action(description: str, name: str | None = None) -> None:
    project_root = get_project_root()
    local_actions_dir = project_root / "musicsheets" / "local_actions"

    if not local_actions_dir.exists():
        print(
            "Error: local_actions/ not found. "
            "Run this command from an initialized Orchestra project.",
            file=sys.stderr,
        )
        sys.exit(1)

    prompt_path = Path(__file__).parent / "compose_action.md"
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    builtin_integrations = _read_index(ACTIONS_DIR / "integrations" / "integration_index.json")
    local_action_index = _read_index(project_root / "musicsheets" / "local_actions" / "action_index.json")
    local_integrations = _read_index(project_root / "musicsheets" / "local_actions" / "local_integrations" / "integration_index.json")

    integration_summary = _format_actions(builtin_integrations + local_integrations)

    all_secrets = set()
    for entry in builtin_integrations + local_integrations:
        for key in entry.get("secrets", []):
            all_secrets.add(key)

    secrets_context = ""
    if all_secrets:
        secrets_context = "\n".join(f"- {k}" for k in sorted(all_secrets))

    existing_files_context = "(No existing local actions)"
    local_files = sorted(p for p in local_actions_dir.glob("*.py") if p.name != "__init__.py")
    if local_files:
        lines = []
        for lf in local_files:
            funcs = []
            for entry in local_action_index:
                if entry.get("module", "") == f"local_actions.{lf.stem}":
                    funcs.append(f"  {entry['function']}({entry.get('signature', '')})")
            if funcs:
                lines.append(f"{lf.name}:")
                lines.extend(funcs)
        if lines:
            existing_files_context = "\n".join(lines)

    stem = name or _slugify(description)
    target_path = local_actions_dir / f"{stem}.py"

    print(f"[*] Generating action: {description}")

    retry_prompt = (
        "The previous response contained invalid Python code. "
        "Please output ONLY valid Python with no markdown fences or extra text.\n\n"
    )

    user_message = (
        "## Available Integrations (for API/credential access)\n\n"
        f"{integration_summary}\n\n"
        "## Available Secret Key Names (use via integrations, not directly)\n\n"
        f"{secrets_context or '(None)'}\n\n"
        "## Existing Local Action Files (append to matching file if related)\n\n"
        f"{existing_files_context}\n\n"
        "## Request\n\n"
        f"Generate an action function for: {description}\n\n"
        f"Output path: local_actions/{stem}.py"
    )

    code = None
    for attempt in range(1, MAX_RETRIES + 1):
        code = llm_query(system_prompt, user_message)
        code = _strip_markdown_fences(code)

        error = _validate_python(code, f"local_actions/{stem}.py")
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

    _write_action(local_actions_dir, f"{stem}.py", code)
    print(f"[+] Action written to local_actions/{stem}.py")

    build_action_index()
    build_local_action_index(project_root)


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

    builtin_integrations = _read_index(ACTIONS_DIR / "integrations" / "integration_index.json")
    local_integrations = _read_index(project_root / "musicsheets" / "local_actions" / "local_integrations" / "integration_index.json")

    integration_summary = _format_actions(builtin_integrations + local_integrations)

    all_secrets = set()
    for entry in builtin_integrations + local_integrations:
        for key in entry.get("secrets", []):
            all_secrets.add(key)

    secrets_context = ""
    if all_secrets:
        secrets_context = "\n".join(f"- {k}" for k in sorted(all_secrets))

    stem = name or _slugify(description)
    target_path = local_integrations_dir / f"{stem}.py"

    print(f"[*] Generating integration: {description}")

    retry_prompt = (
        "The previous response contained invalid Python code. "
        "Please output ONLY valid Python with no markdown fences or extra text.\n\n"
    )

    user_message = (
        "## Existing Integrations (do not duplicate)\n\n"
        f"{integration_summary}\n\n"
        "## Available Secret Key Names (use with get_secret() only)\n\n"
        f"{secrets_context or '(None)'}\n\n"
        "## Request\n\n"
        f"Generate an integration module for: {description}\n\n"
        f"Output path: local_actions/local_integrations/{stem}.py"
    )

    code = None
    for attempt in range(1, MAX_RETRIES + 1):
        code = llm_query(system_prompt, user_message)
        code = _strip_markdown_fences(code)

        error = _validate_python(code, f"local_integrations/{stem}.py")
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

    _write_action(local_integrations_dir, f"{stem}.py", code)
    print(f"[+] Integration written to local_actions/local_integrations/{stem}.py")

    build_integration_index()
    build_local_integration_index(project_root)
