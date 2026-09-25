"""Provided-source model contracts backed by a maintainer-installed, verified release."""

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from coastmas.adapters.projection_pursuit import ProjectionPursuitAdapter
from coastmas.configuration import configuration_value
from coastmas.core.contracts import Contract, ModelSpec, VariableSpec
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import RegisteredRuntime, model_identity

Method = Literal["ppci_mcdc", "ppr_ols"]
METHODS: dict[Method, tuple[str, str]] = {
    "ppci_mcdc": ("PPCI 投影寻踪聚类", "GPL-3"),
    "ppr_ols": ("pprRFA 投影寻踪回归", "MIT"),
}


class ProjectionRelease(Contract):
    image: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    proof_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    clustering_pair_disagreements: int = Field(strict=True, ge=0, le=0)
    regression_max_abs_error: float = Field(ge=0, le=1e-12)


def release() -> ProjectionRelease:
    try:
        path = configuration_value("COASTMAS_PROJECTION_RELEASE")
    except RuntimeError as exc:
        raise CoastMASError("MODEL_ERROR", "provided model release is not configured") from exc
    try:
        installed = ProjectionRelease.model_validate_json(Path(path).read_text())
        proof_bytes = Path(path).with_suffix(".proof.json").read_bytes()
        if hashlib.sha256(proof_bytes).hexdigest() != installed.proof_sha256:
            raise ValueError("technical proof checksum differs")
        proof = json.loads(proof_bytes)
        if not isinstance(proof, dict) or any(
            proof.get(key) != getattr(installed, key)
            for key in ("image", "clustering_pair_disagreements", "regression_max_abs_error")
        ):
            raise ValueError("technical proof differs from release")
        if proof.get("scope") != "technical_iris_fixture_not_coastal_scientific_validation":
            raise ValueError("technical proof scope missing")
        return installed
    except (ValueError, OSError) as exc:
        raise CoastMASError("MODEL_ERROR", "provided model release is invalid") from exc


def projection_model(project: str, method: Method, *, approved: bool = False) -> ModelSpec:
    installed = release()
    name, license = METHODS[method]

    def variable(name: str, standard: str) -> VariableSpec:
        return VariableSpec(
            name=name,
            standard_name=standard,
            description=(
                "Explicit row identifiers, feature units and preprocessing; numeric table payload"
            ),
            data_type="json",
            unit="1",
            dimension="dimensionless",
            semantic_type="continuous",
            spatial_support="observation",
            temporal_support="declared_period",
            aggregation_type="intensive",
            nodata_policy="reject",
            required=True,
        )

    size = "clusters" if method == "ppci_mcdc" else "terms"
    stamp = datetime(2026, 9, 23, tzinfo=UTC)
    return ModelSpec.model_validate(
        {
            "id": f"business:{project}:{method}",
            "name": name,
            "display_name": name,
            "version": 1,
            "model_type": "STATISTICAL",
            "description": (
                "User-provided R implementation. Technical comparison is not coastal business "
                "validation. Maximum 10000 explicit observations; no silent sampling."
            ),
            "capabilities": [method],
            "scientific_domain": ["projection_pursuit"],
            "inputs": [variable("frame", "projection_pursuit_frame")],
            "outputs": [variable("result", "projection_pursuit_result")],
            "parameters": [
                {
                    "name": size,
                    "unit": "1",
                    "minimum": 2 if size == "clusters" else 1,
                    "maximum": 20,
                    "default": 2 if size == "clusters" else 1,
                    "required": True,
                },
                {
                    "name": "seed",
                    "unit": "1",
                    "minimum": 0,
                    "maximum": 2147483647,
                    "default": 42,
                    "required": True,
                },
            ],
            "spatial_scale": {"minimum": 1, "maximum": 1e9, "unit": "m"},
            "temporal_scale": {"minimum": 1, "maximum": 1e12, "unit": "s"},
            "supported_geometry": ["point", "grid", "polygon", "multipolygon"],
            "supported_crs": ["EPSG:4326", "EPSG:32648", "EPSG:32650"],
            "runtime_type": "docker",
            "runtime_config": {"handler": method, **installed.model_dump(mode="json")},
            "constraints": [],
            "enabled": True,
            "validation_status": "VALIDATED" if approved else "UNVALIDATED",
            "execution_status": "EXECUTABLE" if approved else "NOT_EXECUTABLE",
            "validation_metrics": {
                "original_implementation_max_abs_error": installed.regression_max_abs_error
                if method == "ppr_ols"
                else 0
            }
            if approved
            else {},
            "references": ["docs/business-integration-repair-task.md"],
            "owner": "CoastMAS reviewed source release",
            "license": license,
            "created_at": stamp,
            "updated_at": stamp,
        }
    )


def verified_runtime(model: ModelSpec, *, allow_unapproved: bool = False) -> RegisteredRuntime:
    parts = model.id.split(":")
    if len(parts) != 3 or parts[0] != "business" or parts[2] not in METHODS:
        raise CoastMASError("MODEL_ERROR", "not a registered provided model")
    method = parts[2]
    expected = projection_model(parts[1], method, approved=not allow_unapproved)
    mutable = {"version", "enabled", "updated_at"}
    if model.model_dump(exclude=mutable) != expected.model_dump(exclude=mutable):
        raise CoastMASError("MODEL_ERROR", "model differs from reviewed source contract")
    docker = shutil.which("docker")
    if docker is None:
        raise CoastMASError("MODEL_ERROR", "Docker runtime unavailable")
    adapter = ProjectionPursuitAdapter(image=release().image, docker=docker)
    return RegisteredRuntime(model_identity(model), adapter, method)
