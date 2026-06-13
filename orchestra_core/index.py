import ast
import json
import logging
import re
from pathlib import Path

from orchestra_core.config import ACTIONS_DIR

logger = logging.getLogger(__name__)

GET_SECRET_PATTERN = re.compile(r'get_secret\("([^"]+)"\)')


def _extract_secret_keys(filepath: Path) -> list[str]:
    """Scan a Python source file for get_secret("<KEY>") calls and return the keys."""
    keys = set()
    try:
        with open(filepath) as f:
            source = f.read()
        for key in GET_SECRET_PATTERN.findall(source):
            keys.add(key)
    except Exception:
        pass
    return sorted(keys)


def _build_signature_from_ast(args: ast.arguments, returns: ast.expr | None) -> str:
    """Build a signature string from an AST arguments node."""
    parts = []

    num_args = len(args.args)
    num_defaults = len(args.defaults)
    default_offset = num_args - num_defaults

    for i, arg in enumerate(args.args):
        part = arg.arg
        if arg.annotation:
            part += f": {ast.unparse(arg.annotation)}"
        default_idx = i - default_offset
        if default_idx >= 0:
            part += f" = {ast.unparse(args.defaults[default_idx])}"
        parts.append(part)

    if args.vararg:
        part = f"*{args.vararg.arg}"
        if args.vararg.annotation:
            part += f": {ast.unparse(args.vararg.annotation)}"
        parts.append(part)
    elif args.kwonlyargs:
        parts.append("*")

    for i, arg in enumerate(args.kwonlyargs):
        part = arg.arg
        if arg.annotation:
            part += f": {ast.unparse(arg.annotation)}"
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            part += f" = {ast.unparse(args.kw_defaults[i])}"
        parts.append(part)

    if args.kwarg:
        part = f"**{args.kwarg.arg}"
        if args.kwarg.annotation:
            part += f": {ast.unparse(args.kwarg.annotation)}"
        parts.append(part)

    sig = f"({', '.join(parts)})"
    if returns:
        sig += f" -> {ast.unparse(returns)}"
    return sig


def _get_docstring_from_ast(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extract the docstring from a function's AST node."""
    if not func_node.body:
        return ""
    first_stmt = func_node.body[0]
    if (
        isinstance(first_stmt, ast.Expr)
        and isinstance(first_stmt.value, ast.Constant)
        and isinstance(first_stmt.value.value, str)
    ):
        return first_stmt.value.value
    return ""


def _build_func_index_from_dir(
    directory: Path, module_prefix: str, output_json_path: Path
) -> dict:
    """Scan .py files in a directory and return a grouped dict index.

    Each entry contains a secrets list and functions with signatures
    and docstrings. Writes the result to output_json_path.
    """
    if not directory.exists():
        return {}

    grouped: dict = {}

    for file in directory.glob("*.py"):
        if file.name.startswith("__"):
            continue

        secret_keys = _extract_secret_keys(file)

        module_name = f"{module_prefix}.{file.stem}"
        try:
            source = file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file))
        except Exception as e:
            logger.warning(
                "index.parse_failed",
                extra={"data": {"module": module_name, "error": str(e)}},
            )
            continue

        functions = []
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue

            sig = _build_signature_from_ast(node.args, node.returns)
            doc = _get_docstring_from_ast(node)

            description = ""
            if doc:
                description = doc.strip().replace("\n", " ").strip()

            functions.append(
                {
                    "function": node.name,
                    "signature": sig,
                    "description": description,
                }
            )

        if functions:
            grouped[module_name] = {"secrets": secret_keys, "functions": functions}

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w") as f:
        json.dump(grouped, f, indent=4)

    return grouped


def build_action_index(project_root: Path) -> dict:
    """Build and merge built-in + local action indexes into a single grouped dict."""
    local_base = project_root / "musicsheets" / "local_actions"

    actions = _build_func_index_from_dir(
        ACTIONS_DIR, "actions", local_base / "builtin_action_index.json"
    )
    actions.update(
        _build_func_index_from_dir(
            local_base, "local_actions", local_base / "local_action_index.json"
        )
    )
    return actions


def build_integration_index(project_root: Path) -> dict:
    """Build and merge built-in + local integration indexes into a single dict."""
    local_base = project_root / "musicsheets" / "local_actions" / "local_integrations"

    integrations = _build_func_index_from_dir(
        ACTIONS_DIR / "integrations",
        "actions.integrations",
        local_base / "builtin_integration_index.json",
    )
    integrations.update(
        _build_func_index_from_dir(
            local_base,
            "local_actions.local_integrations",
            local_base / "local_integration_index.json",
        )
    )
    return integrations
