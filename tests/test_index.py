import sys
from pathlib import Path

from orchestra_core.index import build_action_index, build_integration_index


def test_build_action_index_uses_static_parsing_without_executing_code(tmp_path: Path):
    """Prove that indexing does not execute top-level code in action files."""
    # Create directory structure
    local_actions = tmp_path / "musicsheets" / "local_actions"
    local_actions.mkdir(parents=True)

    # Create evil.py with top-level code that would write a marker file if executed
    marker_file = tmp_path / "marker.txt"
    evil_code = f'''
import pathlib
pathlib.Path("{marker_file}").write_text("EXECUTED")

def safe_function(x: int) -> int:
    """A safe function that should be indexed."""
    return x * 2
'''
    (local_actions / "evil.py").write_text(evil_code)

    # Build index
    result = build_action_index(tmp_path)

    # Assert marker file was NOT created (code was not executed)
    assert not marker_file.exists(), "Top-level code was executed during indexing"

    # Assert the function was still indexed
    assert "local_actions.evil" in result
    assert len(result["local_actions.evil"]["functions"]) == 1
    assert result["local_actions.evil"]["functions"][0]["function"] == "safe_function"


def test_build_action_index_does_not_mutate_sys_path(tmp_path: Path):
    """Prove that build_action_index does not modify sys.path."""
    # Create directory structure
    local_actions = tmp_path / "musicsheets" / "local_actions"
    local_actions.mkdir(parents=True)

    # Snapshot sys.path before
    sys_path_before = sys.path.copy()

    # Build index
    build_action_index(tmp_path)

    # Assert sys.path is unchanged
    assert sys.path == sys_path_before, "sys.path was mutated by build_action_index"


def test_index_extracts_public_functions_signatures_and_docstrings(tmp_path: Path):
    """Verify that public functions are indexed with correct signatures and docstrings."""
    # Create directory structure
    local_actions = tmp_path / "musicsheets" / "local_actions"
    local_actions.mkdir(parents=True)

    # Create test module with various function types
    test_code = '''
def public_function(a: int, b: str = "default") -> dict:
    """This is a public function.

    It has multiple paragraphs in the docstring.
    This second paragraph should not appear in the description.
    """
    return {"a": a, "b": b}


def another_public(*args, **kwargs):
    """Another public function with varargs."""
    pass


def _private_function():
    """This should not be indexed."""
    pass


class SomeClass:
    """Classes should not be indexed."""
    def method(self):
        """Methods should not be indexed."""
        pass
'''
    (local_actions / "test_module.py").write_text(test_code)

    # Build index
    result = build_action_index(tmp_path)

    # Assert module is indexed
    assert "local_actions.test_module" in result

    functions = result["local_actions.test_module"]["functions"]

    # Assert only public functions are indexed (not private or class methods)
    function_names = [f["function"] for f in functions]
    assert "public_function" in function_names
    assert "another_public" in function_names
    assert "_private_function" not in function_names
    assert "method" not in function_names
    assert len(functions) == 2

    # Check public_function signature and description
    public_func = next(f for f in functions if f["function"] == "public_function")
    assert public_func["signature"] == "(a: int, b: str = 'default') -> dict"
    assert public_func["description"] == "This is a public function."

    # Check another_public signature
    another_func = next(f for f in functions if f["function"] == "another_public")
    assert another_func["signature"] == "(*args, **kwargs)"
    assert another_func["description"] == "Another public function with varargs."


def test_build_integration_index_merges_builtin_and_local_integrations(tmp_path: Path):
    """Verify that built-in and local integrations are merged correctly."""
    # Create directory structure
    local_integrations = (
        tmp_path / "musicsheets" / "local_actions" / "local_integrations"
    )
    local_integrations.mkdir(parents=True)

    # Create a local integration
    local_code = '''
from orchestra_core.secrets import get_secret

def get_custom_api_key() -> str:
    """Retrieve the custom API key."""
    return get_secret("CUSTOM_API_KEY")
'''
    (local_integrations / "custom.py").write_text(local_code)

    # Build integration index
    result = build_integration_index(tmp_path)

    # Assert local integration is present
    assert "local_actions.local_integrations.custom" in result
    assert len(result["local_actions.local_integrations.custom"]["functions"]) == 1
    assert (
        result["local_actions.local_integrations.custom"]["functions"][0]["function"]
        == "get_custom_api_key"
    )
    assert (
        "CUSTOM_API_KEY" in result["local_actions.local_integrations.custom"]["secrets"]
    )

    # Assert built-in integrations are still present
    # (slack_integration and virustotal_integration from actions/integrations/)
    assert "actions.integrations.slack_integration" in result
    assert "actions.integrations.virustotal_integration" in result
