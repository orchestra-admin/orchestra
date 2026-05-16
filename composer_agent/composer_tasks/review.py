import json
from pathlib import Path

from orchestra_core.config import ACTIONS_DIR, get_project_root
from orchestra_core.llm import llm_query


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


def review_playbook(playbook_path: str) -> str:
    """Review a playbook markdown file and return structured improvement suggestions."""
    project_root = get_project_root()
    playbook_file = Path(playbook_path)

    prompt_path = Path(__file__).parent / "review_prompt.md"
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    with open(playbook_file, "r") as f:
        playbook_text = f.read()

    from orchestra_core.index import get_actions_index
    all_actions = get_actions_index()

    actions_summary = ""
    if all_actions:
        lines = []
        for mod, info in all_actions.items():
            for func in info["functions"]:
                sig = func.get("signature", "")
                desc = func.get("description", "")
                lines.append(f"- {mod}.{func['function']}{sig}: {desc}")
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

    return llm_query(system_prompt, user_message)
