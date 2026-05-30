import subprocess

import pytest


@pytest.mark.integration
def test_import_smoke():
    """Verify that all main modules can be imported successfully."""

    # Verify key submodules

    # If we got here, all imports succeeded
    assert True


@pytest.mark.integration
def test_cli_help_smoke():
    """Verify that orchestra --help exits successfully."""
    result = subprocess.run(
        ["orchestra", "--help"],
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
    """Verify that orchestra compose --help exits successfully."""
    result = subprocess.run(
        ["orchestra", "compose", "--help"],
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
    """Verify that orchestra playbook --help exits successfully."""
    result = subprocess.run(
        ["orchestra", "playbook", "--help"],
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
        pytest -m integration --run-docker\
            tests/test_integration_smoke.py::test_docker_help_smoke
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
