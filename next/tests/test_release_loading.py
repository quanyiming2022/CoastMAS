"""Preview candidate builds without changing files served by the active release."""

import json
import runpy
from pathlib import Path

import pytest


def test_explicit_isolated_frontend_build_is_respected_and_must_exist(tmp_path):
    load = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/dev.py"))["load"]
    build = tmp_path / "candidate"
    build.mkdir()
    (build / "index.html").write_text("candidate")
    config = tmp_path / "settings.json"
    config.write_text(
        json.dumps(
            {
                "database_url": "sqlite:///" + str(tmp_path / "isolated.db"),
                "storage_root": str(tmp_path / "objects"),
                "web_root": str(build),
            }
        )
    )
    assert load(config).web_root == build.resolve()
    (build / "index.html").unlink()
    with pytest.raises(ValueError, match="build"):
        load(config)
