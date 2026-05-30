from pathlib import Path

import pytest

from orchestra_core.secrets import _get_secret_env, _load_env_file


def test_load_env_file_reads_key_value_pairs(tmp_path: Path):
    """_load_env_file reads simple KEY=VALUE pairs."""
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=secret123\nDB_HOST=localhost\n")

    result = _load_env_file(env_file)
    assert result == {"API_KEY": "secret123", "DB_HOST": "localhost"}


def test_load_env_file_strips_quotes(tmp_path: Path):
    """_load_env_file strips single and double quotes from values."""
    env_file = tmp_path / ".env"
    env_file.write_text('KEY1="value1"\nKEY2=\'value2\'\n')

    result = _load_env_file(env_file)
    assert result == {"KEY1": "value1", "KEY2": "value2"}


def test_load_env_file_ignores_comments(tmp_path: Path):
    """_load_env_file ignores lines starting with #."""
    env_file = tmp_path / ".env"
    env_file.write_text("# This is a comment\nKEY=value\n# Another comment\n")

    result = _load_env_file(env_file)
    assert result == {"KEY": "value"}


def test_load_env_file_ignores_empty_lines(tmp_path: Path):
    """_load_env_file ignores empty lines."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY1=value1\n\n\nKEY2=value2\n")

    result = _load_env_file(env_file)
    assert result == {"KEY1": "value1", "KEY2": "value2"}


def test_load_env_file_ignores_placeholders(tmp_path: Path):
    """_load_env_file ignores placeholder values like <set_in_aws_ssm>."""
    env_file = tmp_path / ".env"
    env_file.write_text("REAL_KEY=real_value\nPLACEHOLDER=<set_in_aws_ssm>\n")

    result = _load_env_file(env_file)
    assert result == {"REAL_KEY": "real_value"}
    assert "PLACEHOLDER" not in result


def test_load_env_file_returns_empty_dict_for_missing_file(tmp_path: Path):
    """_load_env_file returns empty dict when file doesn't exist."""
    result = _load_env_file(tmp_path / "nonexistent.env")
    assert result == {}


def test_get_secret_env_reads_from_env_file(tmp_path: Path, monkeypatch):
    """_get_secret_env reads values from configured .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_SECRET=from_env_file\n")

    # Monkeypatch to use tmp_path as project root
    monkeypatch.setattr("orchestra_core.secrets.get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "orchestra_core.secrets.load_project_config",
        lambda: {
            "secrets": {
                "backend": "env",
                "backend_configs": {"env": {"path": ".env"}},
            }
        },
    )

    # Clear any existing env var
    monkeypatch.delenv("TEST_SECRET", raising=False)

    result = _get_secret_env("TEST_SECRET")
    assert result == "from_env_file"


def test_get_secret_env_prefers_os_environ(tmp_path: Path, monkeypatch):
    """_get_secret_env prefers OS environment variables over .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_SECRET=from_env_file\n")

    monkeypatch.setattr("orchestra_core.secrets.get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "orchestra_core.secrets.load_project_config",
        lambda: {
            "secrets": {
                "backend": "env",
                "backend_configs": {"env": {"path": ".env"}},
            }
        },
    )

    # Set OS environment variable
    monkeypatch.setenv("TEST_SECRET", "from_os_environ")

    result = _get_secret_env("TEST_SECRET")
    assert result == "from_os_environ"


def test_get_secret_env_raises_for_missing_key(tmp_path: Path, monkeypatch):
    """_get_secret_env raises KeyError when key is not found."""
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_KEY=value\n")

    monkeypatch.setattr("orchestra_core.secrets.get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "orchestra_core.secrets.load_project_config",
        lambda: {
            "secrets": {
                "backend": "env",
                "backend_configs": {"env": {"path": ".env"}},
            }
        },
    )

    monkeypatch.delenv("MISSING_KEY", raising=False)

    with pytest.raises(KeyError, match="Secret 'MISSING_KEY' not found"):
        _get_secret_env("MISSING_KEY")


def test_get_secret_env_rejects_placeholder_values(tmp_path: Path, monkeypatch):
    """_get_secret_env raises KeyError for placeholder values in .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("PLACEHOLDER_KEY=<set_in_aws_ssm>\n")

    monkeypatch.setattr("orchestra_core.secrets.get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "orchestra_core.secrets.load_project_config",
        lambda: {
            "secrets": {
                "backend": "env",
                "backend_configs": {"env": {"path": ".env"}},
            }
        },
    )

    monkeypatch.delenv("PLACEHOLDER_KEY", raising=False)

    # _load_env_file filters out placeholders, so the key won't be found
    with pytest.raises(KeyError, match="Secret 'PLACEHOLDER_KEY' not found"):
        _get_secret_env("PLACEHOLDER_KEY")


def test_get_secret_env_handles_absolute_path(tmp_path: Path, monkeypatch):
    """_get_secret_env handles absolute paths in .env config."""
    env_file = tmp_path / "custom.env"
    env_file.write_text("ABS_PATH_KEY=absolute_value\n")

    monkeypatch.setattr("orchestra_core.secrets.get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "orchestra_core.secrets.load_project_config",
        lambda: {
            "secrets": {
                "backend": "env",
                "backend_configs": {"env": {"path": str(env_file)}},
            }
        },
    )

    monkeypatch.delenv("ABS_PATH_KEY", raising=False)

    result = _get_secret_env("ABS_PATH_KEY")
    assert result == "absolute_value"
