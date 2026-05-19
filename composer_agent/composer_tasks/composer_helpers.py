import json
import re
from pathlib import Path

MAX_RETRIES = 3

ComposeResult = tuple[bool, str | None, str | None, list[str]]


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


def _write_action(base_dir: Path, relative_path: str, code: str) -> None:
    if ".." in relative_path or "/" in relative_path or "\\" in relative_path:
        raise ValueError(f"Invalid action filename '{relative_path}': must be a simple .py stem")
    if not relative_path.endswith(".py"):
        raise ValueError(f"Invalid action filename '{relative_path}': must end with .py")

    target = (base_dir / relative_path).resolve()
    try:
        target.relative_to(base_dir.resolve())
    except ValueError:
        raise ValueError(f"Invalid action filename '{relative_path}': path escapes base directory") from None
    target.parent.mkdir(parents=True, exist_ok=True)
    code = code.strip() + "\n"

    if target.exists():
        existing = target.read_text().rstrip()
        combined = existing + "\n\n" + code
    else:
        combined = code

    target.write_text(combined)


def _read_index(path: Path) -> list | dict:
    if not path.exists():
        return []
    with open(path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _read_integration_index(path: Path) -> dict:
    data = _read_index(path)
    if isinstance(data, dict):
        return data
    return {}


def _format_actions(entries: list | dict) -> str:
    if not entries:
        return "(None)"
    lines = []

    if isinstance(entries, dict):
        for mod, info in entries.items():
            for func in info["functions"]:
                sig = func.get("signature", "")
                desc = func.get("description", "")
                lines.append(f"- {mod}.{func['function']}{sig}: {desc}")
    else:
        for entry in entries:
            mod = entry.get("module", "")
            func = entry.get("function", "")
            sig = entry.get("signature", "")
            desc = entry.get("description", "")
            lines.append(f"- {mod}.{func}{sig}: {desc}")

    return "\n".join(lines)
