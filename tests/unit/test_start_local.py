"""Launcher safeguards run without Docker or user services."""

import json
from types import SimpleNamespace

import pytest

from scripts import start_local as launcher


def test_discovers_only_exact_cli_in_this_project(monkeypatch, tmp_path):
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda *a, **k: (
            "10 python -m coastmas api\n11 python -m coastmas worker\n"
            "12 python -m coastmas beat\n13 python -m coastmas worker extra\n"
            "14 python other.py coastmas beat\n"
        ),
    )
    monkeypatch.setattr(
        launcher, "process_directory", lambda pid: tmp_path if pid != 12 else tmp_path / "other"
    )
    assert launcher.discover_services(tmp_path) == {"api": 10, "worker": 11}


def test_duplicate_scheduler_is_reported_without_stopping_it(monkeypatch, tmp_path):
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda *a, **k: "10 python -m coastmas beat\n11 python -m coastmas beat\n",
    )
    monkeypatch.setattr(launcher, "process_directory", lambda pid: tmp_path)
    with pytest.raises(RuntimeError, match="多个 beat"):
        launcher.discover_services(tmp_path)


def test_start_lock_rejects_overlapping_invocation(tmp_path):
    with launcher.start_lock(tmp_path):
        with pytest.raises(RuntimeError, match="另一个启动"):
            with launcher.start_lock(tmp_path):
                pass


@pytest.fixture
def environment(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "check_prerequisites", lambda root: None)
    monkeypatch.setattr(launcher, "ensure_infrastructure", lambda root, logs: None)
    monkeypatch.setattr(launcher, "wait_for_application", lambda processes: None)
    monkeypatch.setattr(launcher, "port_in_use", lambda: False)
    monkeypatch.setattr(launcher, "discover_services", lambda root: {})
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        launcher.os,
        "kill",
        lambda pid, signal: None if signal == 0 else pytest.fail("must never stop a service"),
    )
    started = []

    def spawn(root, service, logs):
        started.append(service)
        return SimpleNamespace(pid=100 + len(started), poll=lambda: None)

    monkeypatch.setattr(launcher, "spawn_service", spawn)
    return tmp_path, started


def test_starts_missing_services_and_reuses_existing(environment, monkeypatch):
    root, started = environment
    monkeypatch.setattr(launcher, "discover_services", lambda root: {"worker": 90})
    result = launcher.start(root)
    assert started == ["beat", "api"]
    assert result["worker"] == 90
    saved = json.loads((root / "artifacts/runtime/start-local/services.json").read_text())
    assert saved == result


def test_repeat_start_does_not_spawn_or_recreate_infrastructure(environment, monkeypatch):
    root, started = environment
    original = {"api": 1, "worker": 2, "beat": 3}
    monkeypatch.setattr(launcher, "discover_services", lambda root: original)
    monkeypatch.setattr(launcher, "port_in_use", lambda: True)
    assert launcher.start(root) == original
    assert started == []


def test_foreign_listener_blocks_before_infrastructure_changes(environment, monkeypatch):
    root, started = environment
    monkeypatch.setattr(launcher, "port_in_use", lambda: True)
    monkeypatch.setattr(
        launcher,
        "ensure_infrastructure",
        lambda *args: pytest.fail("must not change dependencies for a foreign listener"),
    )
    with pytest.raises(RuntimeError, match="58000"):
        launcher.start(root)
    assert started == []


def test_failed_child_does_not_report_ready(monkeypatch):
    monkeypatch.setattr(launcher, "application_ready", lambda: True)
    with pytest.raises(RuntimeError, match="worker"):
        launcher.wait_for_application({"worker": SimpleNamespace(poll=lambda: 1)})


def test_unready_application_times_out(monkeypatch):
    ticks = iter([0, 0, 61])
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(launcher, "application_ready", lambda: False)
    with pytest.raises(RuntimeError, match="未就绪"):
        launcher.wait_for_application({})


def test_missing_frontend_explains_build_requirement(tmp_path, monkeypatch):
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/python").touch()
    (tmp_path / ".env").touch()
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/" + name)
    with pytest.raises(RuntimeError, match="前端"):
        launcher.check_prerequisites(tmp_path)


def test_infrastructure_waits_for_health_without_recreating(monkeypatch, tmp_path):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    launcher.ensure_infrastructure(tmp_path, tmp_path)
    assert "--no-recreate" in commands[0]
    assert "--wait" in commands[0]
    assert "down" not in commands[0]


def test_dependency_failure_is_not_reported_as_success(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError, match="基础服务启动失败"):
        launcher.ensure_infrastructure(tmp_path, tmp_path)
