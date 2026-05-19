from orchestra_core.config import get_project_root
from orchestra_core.index import build_action_index, build_integration_index


def _print_index(title: str, items: list | dict) -> None:
    print(f"\n--- {title} ---\n")

    if isinstance(items, dict):
        if not items:
            print("  (None found)")
            return
        for mod, info in items.items():
            print(f"[{mod}]")
            for func in info["functions"]:
                desc = func.get("description", "")
                if desc:
                    print(f"  - {func['function']}(): {desc}")
                else:
                    print(f"  - {func['function']}()")
            print()
        return

    grouped = {}
    for item in items:
        mod = item["module"]
        grouped.setdefault(mod, []).append(item)

    if not grouped:
        print("  (None found)")
        return

    for mod, funcs in grouped.items():
        print(f"[{mod}]")
        for func in funcs:
            desc = func.get("description", "")
            if desc:
                print(f"  - {func['function']}(): {desc}")
            else:
                print(f"  - {func['function']}()")
        print()


def print_actions():
    """Print all available actions from built-in and local action indices."""
    _print_index("Available Orchestra Actions", build_action_index(get_project_root()))


def print_integrations():
    """Print all available integrations from built-in and local integration indices."""
    _print_index("Available Orchestra Integrations", build_integration_index(get_project_root()))
