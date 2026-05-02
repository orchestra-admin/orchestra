import re
import sys
from pathlib import Path

from conductor_agent.conductor_tasks.llm import llm_query
from conductor_agent.conductor_tasks.config import get_project_root

MAX_RETRIES = 3


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


def _validate_python(code: str) -> str | None:
    try:
        compile(code, "<composer_output>", "exec")
    except SyntaxError as exc:
        return f"SyntaxError on line {exc.lineno}: {exc.msg}"
    return None


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

    print(f"[*] Composing script for {playbook_path}...")

    code_output = None
    retry_prompt = (
        "The previous response contained invalid Python code. "
        "Please output ONLY valid Python code with no markdown fences or extra text.\n\n"
    )

    user_message = f"Here is the playbook to convert: {playbook_text}. Generate the Python script now."

    for attempt in range(1, MAX_RETRIES + 1):
        code_output = llm_query(system_prompt, user_message)
        code_output = _strip_markdown_fences(code_output)

        error = _validate_python(code_output)
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
                "Writing output anyway (script may need manual fixes).",
                file=sys.stderr,
            )

    with open(output_path, "w") as f:
        f.write(code_output)

    print(f"[+] Output written to {output_path}")
