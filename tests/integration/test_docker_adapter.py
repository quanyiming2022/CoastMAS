import subprocess
from uuid import uuid4

import pytest

from coastmas.adapters.docker import ContainerModel, DockerAdapter
from coastmas.adapters.runtime import RunRequest
from coastmas.core.errors import CoastMASError

IMAGE = "sha256:dc11e3ccde3c4defde0194f58c3ec2cf270ed7401560d82d8bd548284b82dfba"
DOCKER = "/usr/local/bin/docker"


def remaining(adapter):
    return subprocess.run(
        [DOCKER, "ps", "-aq", "--filter", f"label=coastmas.adapter={adapter.owner}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_real_container_model_has_readonly_root_and_no_network(tmp_path):
    script = "test ! -w /etc && test -r /work/input.json && printf '{\"result\":42}'"
    adapter = DockerAdapter(
        {"container": ContainerModel(IMAGE, ("/bin/sh", "-c", script))},
        docker=DOCKER,
        owner="test-" + uuid4().hex,
    )
    result = adapter.run(RunRequest("container", {"value": 1}, {}, tmp_path, 10))
    assert result.outputs == {"result": 42}
    assert remaining(adapter) == ""
    assert not list(tmp_path.iterdir())


def test_container_timeout_removes_owned_container_and_does_not_publish(tmp_path):
    adapter = DockerAdapter(
        {"container": ContainerModel(IMAGE, ("/bin/sh", "-c", "sleep 20"))},
        docker=DOCKER,
        owner="test-" + uuid4().hex,
    )
    with pytest.raises(CoastMASError, match="timeout|deadline"):
        adapter.run(RunRequest("container", {}, {}, tmp_path, 1))
    assert remaining(adapter) == ""
    assert not list(tmp_path.iterdir())


def test_mutable_image_tags_are_not_accepted():
    with pytest.raises(CoastMASError, match="digest"):
        DockerAdapter({"container": ContainerModel("redis:latest", ("/bin/true",))}, docker=DOCKER)
