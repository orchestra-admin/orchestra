import os
from pathlib import Path

from orchestra_core.config import get_project_root


def test_get_project_root_uses_current_directory_marker(tmp_path: Path) -> None:
    marker_dir = tmp_path / ".local_config"
    marker_dir.mkdir()
    (marker_dir / "orchestra.json").write_text("{}")

    old_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        assert get_project_root() == tmp_path
    finally:
        os.chdir(old_cwd)


def test_get_project_root_uses_immediate_parent_marker(tmp_path: Path) -> None:
    marker_dir = tmp_path / ".local_config"
    marker_dir.mkdir()
    (marker_dir / "orchestra.json").write_text("{}")
    child = tmp_path / "child"
    child.mkdir()

    old_cwd = Path.cwd()
    os.chdir(child)
    try:
        assert get_project_root() == tmp_path
    finally:
        os.chdir(old_cwd)


def test_get_project_root_ignores_stale_grandparent_marker(tmp_path: Path) -> None:
    marker_dir = tmp_path / ".local_config"
    marker_dir.mkdir()
    (marker_dir / "orchestra.json").write_text("{}")
    cwd = tmp_path / "child" / "grandchild"
    cwd.mkdir(parents=True)

    old_cwd = Path.cwd()
    os.chdir(cwd)
    try:
        assert get_project_root() == cwd
    finally:
        os.chdir(old_cwd)
