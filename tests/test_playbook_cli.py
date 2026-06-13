import json
from pathlib import Path

import pytest

from cli import playbook_cli
from orchestra_core.config import DEACTIVATED_SET_KEY


class _FakeRedis:
    def __init__(self) -> None:
        self.store: set[str] = set()
        self.sadd_calls: list[tuple[str, str]] = []
        self.srem_calls: list[tuple[str, str]] = []
        self.sadd_should_raise: Exception | None = None

    def sadd(self, key: str, *members: str) -> int:
        if self.sadd_should_raise is not None:
            raise self.sadd_should_raise
        for m in members:
            self.store.add(m)
            self.sadd_calls.append((key, m))
        return len(members)

    def srem(self, key: str, *members: str) -> int:
        for m in members:
            self.store.discard(m)
            self.srem_calls.append((key, m))
        return len(members)


def _init_project(
    tmp_path: Path,
    *,
    playbooks: list[str] | None = None,
    musicsheets: list[str] | None = None,
) -> Path:
    if playbooks is not None:
        pb_dir = tmp_path / "playbooks"
        pb_dir.mkdir(parents=True, exist_ok=True)
        for name in playbooks:
            (pb_dir / f"{name}.md").write_text("# stub\n")

    if musicsheets is not None:
        ms_dir = tmp_path / "musicsheets"
        ms_dir.mkdir(parents=True, exist_ok=True)
        for name in musicsheets:
            (ms_dir / f"{name}.py").write_text("# stub\n")

    return tmp_path


def test_deactivate_writes_config_and_redis(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """CLI deactivate updates both config and Redis."""
    _init_project(tmp_path, musicsheets=["ip_enrichment"])
    redis_client = _FakeRedis()
    monkeypatch.setattr(playbook_cli, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(playbook_cli, "get_redis_client", lambda: redis_client)

    playbook_cli.deactivate_playbook("ip_enrichment")

    out = capsys.readouterr().out
    assert "deactivated" in out
    config_path = tmp_path / ".local_config" / "orchestra.json"
    with open(config_path) as f:
        data = json.load(f)
    assert data["playbooks"]["deactivated"] == ["ip_enrichment"]
    assert redis_client.store == {"ip_enrichment"}
    assert redis_client.sadd_calls == [(DEACTIVATED_SET_KEY, "ip_enrichment")]


def test_activate_writes_config_and_redis(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """CLI activate updates both config and Redis."""
    _init_project(tmp_path, musicsheets=["ip_enrichment"])
    redis_client = _FakeRedis()
    redis_client.store.add("ip_enrichment")
    config_dir = tmp_path / ".local_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "orchestra.json").write_text(
        json.dumps({"playbooks": {"deactivated": ["ip_enrichment"]}})
    )
    monkeypatch.setattr(playbook_cli, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(playbook_cli, "get_redis_client", lambda: redis_client)

    playbook_cli.activate_playbook("ip_enrichment")

    out = capsys.readouterr().out
    assert "activated" in out
    with open(config_dir / "orchestra.json") as f:
        data = json.load(f)
    assert data["playbooks"]["deactivated"] == []
    assert redis_client.store == set()
    assert redis_client.srem_calls == [(DEACTIVATED_SET_KEY, "ip_enrichment")]


def test_deactivate_idempotent_keeps_redis_state(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Duplicate CLI deactivate is idempotent and leaves Redis untouched."""
    _init_project(tmp_path, musicsheets=["ip_enrichment"])
    redis_client = _FakeRedis()
    redis_client.store.add("ip_enrichment")
    config_dir = tmp_path / ".local_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "orchestra.json").write_text(
        json.dumps({"playbooks": {"deactivated": ["ip_enrichment"]}})
    )
    monkeypatch.setattr(playbook_cli, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(playbook_cli, "get_redis_client", lambda: redis_client)

    playbook_cli.deactivate_playbook("ip_enrichment")

    out = capsys.readouterr().out
    assert "already inactive" in out
    assert redis_client.sadd_calls == []


def test_activate_idempotent_removes_from_redis(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Duplicate CLI activate is idempotent and never touches Redis."""
    _init_project(tmp_path)
    redis_client = _FakeRedis()
    monkeypatch.setattr(playbook_cli, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(playbook_cli, "get_redis_client", lambda: redis_client)

    playbook_cli.activate_playbook("ip_enrichment")

    out = capsys.readouterr().out
    assert "already active" in out
    assert redis_client.srem_calls == []


def test_invalid_event_type_rejected_without_side_effects(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Invalid event types raise before writing config or Redis."""
    _init_project(tmp_path)
    redis_client = _FakeRedis()
    monkeypatch.setattr(playbook_cli, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(playbook_cli, "get_redis_client", lambda: redis_client)

    with pytest.raises(ValueError):
        playbook_cli.deactivate_playbook("bad/event")

    assert not (tmp_path / ".local_config" / "orchestra.json").exists()
    assert redis_client.sadd_calls == []


def test_print_playbooks_reads_status_from_config(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """print_playbooks reflects durable config even without Redis."""
    _init_project(tmp_path, playbooks=["alpha", "beta"])
    config_dir = tmp_path / ".local_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "orchestra.json").write_text(
        json.dumps({"playbooks": {"deactivated": ["beta"]}})
    )

    def _raise_redis():
        raise RuntimeError("redis is down")

    monkeypatch.setattr(playbook_cli, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(playbook_cli, "get_redis_client", _raise_redis)

    playbook_cli.print_playbooks()

    out = capsys.readouterr().out
    assert "alpha" in out and "active" in out
    assert "beta" in out and "inactive" in out


def test_deactivate_redis_failure_does_not_block(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """If Redis sadd fails after config is written, the CLI still reports success."""
    _init_project(tmp_path, musicsheets=["ip_enrichment"])
    redis_client = _FakeRedis()
    redis_client.sadd_should_raise = RuntimeError("redis is down")
    monkeypatch.setattr(playbook_cli, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(playbook_cli, "get_redis_client", lambda: redis_client)

    playbook_cli.deactivate_playbook("ip_enrichment")

    out = capsys.readouterr().out
    assert "deactivated" in out
    config_path = tmp_path / ".local_config" / "orchestra.json"
    with open(config_path) as f:
        data = json.load(f)
    assert data["playbooks"]["deactivated"] == ["ip_enrichment"]


def test_run_playbook_status_line_appears_before_subprocess_output(
    tmp_path, monkeypatch, capsys
):
    """The 'Running playbook...' line is flushed before the subprocess runs.

    Regression for the bug where the status line was buffered and
    appeared after the subprocess's captured stderr instead of before,
    because the print went to a block-buffered stdout that did not
    flush until the next stdout write.
    """
    from conductor.conductor_tasks.musician import ExecutionResult

    def _fake_execute_job(job, project_root=None, timeout_seconds=300):
        return ExecutionResult(
            status="failed",
            event_type=job["event_type"],
            returncode=1,
            stdout="",
            stderr="boom!",
        )

    monkeypatch.setattr(playbook_cli, "execute_job", _fake_execute_job)
    monkeypatch.setattr(playbook_cli, "get_project_root", lambda: tmp_path)

    playbook_cli.run_playbook("failer", payload={"ip": "1.1.1.1"})

    captured = capsys.readouterr()
    out = captured.out
    err = captured.err

    status_pos = out.find("Running playbook 'failer'")
    failure_pos = out.find("failed with exit code")
    assert status_pos != -1, "status line missing from stdout"
    assert failure_pos != -1, "failure summary missing from stdout"
    assert status_pos < failure_pos, (
        "'Running playbook...' must appear before the failure summary"
    )
    assert "boom!" in err, "subprocess stderr must be re-emitted to stderr"
