"""Independent startup cannot reset a namespace or race its database schema."""

import concurrent.futures
import hashlib
import importlib.util
import threading
from pathlib import Path

import pytest
from coastmas_next.config import Settings
from coastmas_next.store import Store


def test_sqlite_first_initialization_is_serialized(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/new.db", storage_root=tmp_path / "objects"
    )
    barrier = threading.Barrier(2)

    def initialize(_):
        store = Store(settings)
        try:
            barrier.wait(timeout=5)
            store.initialize()
        finally:
            store.engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        list(pool.map(initialize, range(2)))


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        "test_" + name, Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_clean_bootstrap_never_overwrites_existing_namespace(tmp_path, monkeypatch):
    module = load_script("bootstrap")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    result = module.initialize("safe", "admin@example.test", [])
    access = Path(result["access_file"])
    before = hashlib.sha256(access.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        module.initialize("safe", "admin@example.test", [])
    assert hashlib.sha256(access.read_bytes()).hexdigest() == before
    assert access.stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError):
        module.initialize("../outside", "admin@example.test", [])


def test_worker_finishes_current_call_before_stopping():
    module = load_script("dev")
    stop = threading.Event()
    events = []

    class Worker:
        def run_once(self):
            events.append("start")
            stop.set()
            events.append("finish")
            return True

    module.run_worker(Worker(), stop)
    assert events == ["start", "finish"]
