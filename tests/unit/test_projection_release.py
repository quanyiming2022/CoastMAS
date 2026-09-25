import hashlib
import json

import pytest

from coastmas.core.errors import CoastMASError
from coastmas.domain.projection_catalog import release


def test_release_requires_actual_matching_proof(monkeypatch, tmp_path):
    proof = {
        "image": "sha256:" + "a" * 64,
        "clustering_pair_disagreements": 0,
        "regression_max_abs_error": 0.0,
        "scope": "technical_iris_fixture_not_coastal_scientific_validation",
    }
    content = json.dumps(proof).encode()
    config = {
        **{
            k: proof[k]
            for k in ("image", "clustering_pair_disagreements", "regression_max_abs_error")
        },
        "source_sha256": "c" * 64,
        "proof_sha256": hashlib.sha256(content).hexdigest(),
    }
    path = tmp_path / "release.json"
    path.write_text(json.dumps(config))
    monkeypatch.setenv("COASTMAS_PROJECTION_RELEASE", str(path))
    with pytest.raises(CoastMASError):
        release()
    path.with_suffix(".proof.json").write_bytes(content)
    assert release().image == proof["image"]
    path.with_suffix(".proof.json").write_bytes(content + b" ")
    with pytest.raises(CoastMASError):
        release()


def test_unconfigured_release_is_an_explicit_model_error(monkeypatch):
    monkeypatch.setenv("COASTMAS_PROJECTION_RELEASE", "")
    with pytest.raises(CoastMASError, match="not configured"):
        release()
