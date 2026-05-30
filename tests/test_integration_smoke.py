import subprocess
import sys

import pytest


@pytest.mark.integration
def test_import_smoke():
    """Verify that all main modules can be imported successfully."""
    import orchestra
    import cli
    import orchestra_core
    import composer_agent
    import conductor
    import actions

    # Verify key submodules
    from orchestra_core import config, secrets, index, llm, redis, logging, exceptions
    from composer_agent import composer
    from composer_agent.composer_tasks import compose_action, compose_integration, composer_helpers, review
    from conductor.conductor_tasks import musician, webhook, scheduler
    from cli import compose_cli, playbook_cli, init_cli, index_cli, schedule_cli, musician_cli, server_cli, scheduler_cli, secrets_cli

    # If we got here, all imports succeeded
    assert True


@pytest.mark.integration
def test_cli_help_smoke():
    """Verify that orchestra.py --help exits successfully."""
    result = subprocess.run(
        [sys.executable, "orchestra.py", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Orchestra SOAR CLI" in result.stdout
    assert "compose" in result.stdout
    assert "playbook" in result.stdout


@pytest.mark.integration
def test_cli_compose_help_smoke():
    """Verify that orchestra.py compose --help exits successfully."""
    result = subprocess.run(
        [sys.executable, "orchestra.py", "compose", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "playbook" in result.stdout
    assert "action" in result.stdout
    assert "integration" in result.stdout


@pytest.mark.integration
def test_cli_playbook_help_smoke():
    """Verify that orchestra.py playbook --help exits successfully."""
    result = subprocess.run(
        [sys.executable, "orchestra.py", "playbook", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "list" in result.stdout
    assert "activate" in result.stdout
    assert "deactivate" in result.stdout
    assert "run" in result.stdout


@pytest.mark.integration
@pytest.mark.skip(reason="Docker smoke test requires Docker daemon and is slow")
def test_docker_help_smoke():
    """Verify that orchestra --help runs inside Docker image.

    This test is skipped by default because:
    - Requires Docker daemon to be running
    - Docker build is slow (~30-60 seconds)
    - Not needed for fast CI feedback

    To run manually:
        pytest -m integration --run-docker tests/test_integration_smoke.py::test_docker_help_smoke
    """
    # Build Docker image
    build_result = subprocess.run(
        ["docker", "build", "-t", "orchestra-test", "."],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert build_result.returncode == 0, f"Docker build failed: {build_result.stderr}"

    # Run orchestra --help inside container
    run_result = subprocess.run(
        ["docker", "run", "--rm", "orchestra-test", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert run_result.returncode == 0
    assert "Orchestra SOAR CLI" in run_result.stdout
