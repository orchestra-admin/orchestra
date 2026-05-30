from pathlib import Path

import pytest

from composer_agent.composer_tasks.composer_helpers import _write_action


def test_write_action_accepts_simple_py_filename(tmp_path: Path):
    """_write_action accepts simple .py filenames."""
    _write_action(tmp_path, "test.py", "def foo(): pass")
    assert (tmp_path / "test.py").exists()
    assert "def foo(): pass" in (tmp_path / "test.py").read_text()


def test_write_action_appends_to_existing_file(tmp_path: Path):
    """_write_action appends to existing files inside the base directory."""
    (tmp_path / "existing.py").write_text("def first(): pass")

    _write_action(tmp_path, "existing.py", "def second(): pass")

    content = (tmp_path / "existing.py").read_text()
    assert "def first(): pass" in content
    assert "def second(): pass" in content


def test_write_action_rejects_dotdot_slash(tmp_path: Path):
    """_write_action rejects ../x.py."""
    with pytest.raises(
        ValueError, match="path escapes base directory or has traversal characters"
    ):
        _write_action(tmp_path, "../escape.py", "def evil(): pass")


def test_write_action_rejects_nested_paths(tmp_path: Path):
    """_write_action rejects nested/x.py."""
    with pytest.raises(
        ValueError, match="path escapes base directory or has traversal characters"
    ):
        _write_action(tmp_path, "nested/file.py", "def evil(): pass")


def test_write_action_rejects_backslash_paths(tmp_path: Path):
    """_write_action rejects nested\\x.py."""
    with pytest.raises(
        ValueError, match="path escapes base directory or has traversal characters"
    ):
        _write_action(tmp_path, "nested\\file.py", "def evil(): pass")


def test_write_action_rejects_non_py_names(tmp_path: Path):
    """_write_action rejects names without .py."""
    with pytest.raises(ValueError, match="must end with .py"):
        _write_action(tmp_path, "test.txt", "not python")


def test_write_action_rejects_no_extension(tmp_path: Path):
    """_write_action rejects names without any extension."""
    with pytest.raises(ValueError, match="must end with .py"):
        _write_action(tmp_path, "noextension", "not python")


def test_write_action_rejects_escape_via_resolve(tmp_path: Path):
    """_write_action rejects attempts that resolve outside the base directory."""
    # Create a symlink that points outside the base directory
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "escaped.py"
    outside_file.write_text("# outside")

    # Create a symlink inside base_dir that points to the outside file
    symlink_path = tmp_path / "symlink.py"
    try:
        symlink_path.symlink_to(outside_file)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")

    # _write_action should detect the escape via resolve()
    with pytest.raises(ValueError, match="path escapes base directory"):
        _write_action(tmp_path, "symlink.py", "def evil(): pass")
