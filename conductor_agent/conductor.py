import json
import sys
from pathlib import Path

from conductor_agent.conductor_tasks.config import (
    ACTIONS_DIR,
    DEFAULT_QUEUE_KEY,
    DEFAULT_DLQ_KEY,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_BLOCK_SECONDS,
    get_project_root,
    get_project_config_path,
    load_musician_config,
)
from conductor_agent.conductor_tasks.init import init_project
from conductor_agent.conductor_tasks.musician import (
    load_redis_module,
    parse_job,
    build_queue_job,
    enqueue_job,
    run_musician,
)
from conductor_agent.conductor_tasks.index import print_actions, print_integrations
from conductor_agent.conductor_tasks.playbook import print_playbooks, activate_playbook, deactivate_playbook, run_playbook
from conductor_agent.conductor_tasks.schedule_cli import list_schedules, add_schedule, remove_schedule
from conductor_agent.conductor_tasks.scheduler import run_scheduler
from conductor_agent.conductor_tasks.webhook import start_server
from conductor_agent.conductor_tasks.llm import llm_query
from conductor_agent.conductor_tasks.secrets_cli import push_secrets, list_secrets


def _read_action_index(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return json.load(f)


def _summarise_playbook(path: Path) -> str:
    try:
        with open(path, "r") as f:
            lines = f.readlines()
    except Exception:
        return ""
    first_line = lines[0].strip() if lines else ""
    description_lines = []
    in_description = False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "## Description":
            in_description = True
            continue
        if in_description:
            if stripped.startswith("## "):
                break
            if stripped:
                description_lines.append(stripped)
    description = " ".join(description_lines) if description_lines else ""
    if description:
        return f"{first_line} — {description}"
    return first_line


def review_playbook(playbook_path: str) -> None:
    project_root = get_project_root()
    playbook_file = Path(playbook_path)

    if not playbook_file.exists():
        print(f"Error: Playbook not found: {playbook_path}", file=sys.stderr)
        sys.exit(1)

    if not playbook_file.is_file():
        print(f"Error: Not a file: {playbook_path}", file=sys.stderr)
        sys.exit(1)

    prompt_path = Path(__file__).resolve().parent / "review_prompt.md"
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    with open(playbook_file, "r") as f:
        playbook_text = f.read()

    action_index_path = ACTIONS_DIR / "actions_index.json"
    local_action_index_path = project_root / "musicsheets" / "local_actions" / "action_index.json"

    actions = _read_action_index(action_index_path)
    local_actions = _read_action_index(local_action_index_path)
    all_actions = actions + local_actions

    actions_summary = ""
    if all_actions:
        lines = []
        for entry in all_actions:
            module = entry.get("module", "")
            function = entry.get("function", "")
            sig = entry.get("signature", "")
            desc = entry.get("description", "")
            lines.append(f"- {module}.{function}{sig}: {desc}")
        actions_summary = "\n".join(lines)
    else:
        actions_summary = "(No actions available)"

    template_path = project_root / "playbooks" / "template.md"
    if template_path.exists():
        with open(template_path, "r") as f:
            template_text = f.read()
    else:
        template_text = "(No template found)"

    playbooks_dir = project_root / "playbooks"
    existing_summaries = []
    if playbooks_dir.exists():
        for pb in sorted(playbooks_dir.glob("*.md")):
            if pb.name == "template.md" or pb.resolve() == playbook_file.resolve():
                continue
            summary = _summarise_playbook(pb)
            if summary:
                existing_summaries.append(f"- {pb.name}: {summary}")
            else:
                existing_summaries.append(f"- {pb.name}")

    existing_playbooks_text = "\n".join(existing_summaries) if existing_summaries else "(No other playbooks found)"

    user_message = (
        f"## Playbook to Review\n\n{playbook_text}\n\n"
        f"## Available Actions\n\n{actions_summary}\n\n"
        f"## Playbook Template Structure\n\n{template_text}\n\n"
        f"## Existing Playbooks\n\n{existing_playbooks_text}"
    )

    print(f"[*] Reviewing playbook: {playbook_path}...")
    result = llm_query(system_prompt, user_message)

    print(result)
