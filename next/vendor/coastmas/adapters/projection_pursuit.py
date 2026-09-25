"""Strict tabular boundary to the provided R implementations in a pinned container."""

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, ValidationError, model_validator

from coastmas.adapters.docker import ContainerModel, DockerAdapter
from coastmas.adapters.runtime import OUTPUT_SCHEMA, RunRequest
from coastmas.core.contracts import UNITS, Contract, Name
from coastmas.core.errors import CoastMASError, ConstraintError

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class ProjectionFrame(Contract):
    row_ids: tuple[Name, ...] = Field(min_length=4, max_length=10000)
    feature_names: tuple[Name, ...] = Field(min_length=1, max_length=64)
    feature_units: tuple[Name, ...] = Field(min_length=1, max_length=64)
    values: tuple[tuple[Number, ...], ...] = Field(min_length=4, max_length=10000)
    standardize: StrictBool
    response: tuple[Number, ...] | None = None
    response_unit: Name | None = None
    locations: tuple[tuple[Number, Number], ...] | None = None
    observation_scope: Literal["sample_only", "all_joint_valid_cells"] | None = None
    joint_valid_cells: int | None = Field(default=None, strict=True, ge=4)

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        if len(set(self.row_ids)) != len(self.row_ids) or len(set(self.feature_names)) != len(
            self.feature_names
        ):
            raise ValueError("row and feature identifiers must be unique")
        if len(self.row_ids) != len(self.values) or any(
            len(row) != len(self.feature_names) for row in self.values
        ):
            raise ValueError("matrix dimensions differ from identifiers")
        if len(self.feature_units) != len(self.feature_names):
            raise ValueError("each feature requires its own unit")
        if self.response is not None and (
            len(self.response) != len(self.values) or not self.response_unit
        ):
            raise ValueError("response requires matching rows and an explicit unit")
        if self.locations is not None and (
            len(self.locations) != len(self.row_ids)
            or any(abs(lon) > 180 or abs(lat) > 90 for lon, lat in self.locations)
        ):
            raise ValueError("locations require one valid longitude/latitude per row")
        if self.observation_scope is not None and self.joint_valid_cells is None:
            raise ValueError("declared observation scope requires a complete denominator")
        if self.observation_scope == "all_joint_valid_cells" and self.joint_valid_cells != len(
            self.row_ids
        ):
            raise ValueError("full coverage must contain every jointly valid observation")
        if self.joint_valid_cells is not None and self.joint_valid_cells < len(self.row_ids):
            raise ValueError("joint denominator is smaller than selected observations")
        for unit in (*self.feature_units, *((self.response_unit,) if self.response_unit else ())):
            try:
                UNITS.parse_units(unit)
            except Exception as exc:
                raise ValueError("unknown feature or response unit") from exc
        return self


class ProjectionPursuitAdapter(DockerAdapter):
    def __init__(self, *, image: str, docker: str):
        super().__init__(
            {
                name: ContainerModel(
                    image=image,
                    command=("/usr/bin/Rscript", "--vanilla", "/opt/coastmas/runner.R", name),
                    cpus=2,
                    memory_mb=1024,
                    pids=128,
                )
                for name in ("ppci_mcdc", "ppr_ols")
            },
            docker=docker,
            max_output_bytes=4 * 1024 * 1024,
        )

    def validate(self, request: RunRequest) -> None:
        try:
            if set(request.inputs) != {"frame"}:
                raise ValueError("exactly one tabular frame input is required")
            frame = ProjectionFrame.model_validate(request.inputs["frame"])
            key = "clusters" if request.handler == "ppci_mcdc" else "terms"
            if set(request.parameters) != {key, "seed"}:
                raise ValueError("explicit model size and seed parameters are required")
            for name, maximum in ((key, min(20, len(frame.row_ids) - 1)), ("seed", 2147483647)):
                value = request.parameters[name]
                minimum = 2 if name == "clusters" else (1 if name == "terms" else 0)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (float, int))
                    or not minimum <= value <= maximum
                    or value != int(value)
                ):
                    raise ValueError("model size and seed must be bounded integers")
            if request.handler == "ppr_ols" and frame.response is None:
                raise ValueError("regression requires response values and their unit")
            if request.handler == "ppci_mcdc" and frame.response is not None:
                raise ValueError("clustering does not use a response variable")
        except (ValidationError, ValueError) as exc:
            raise ConstraintError(str(exc)) from exc
        super().validate(request)

    def execute(self, request: RunRequest, directory: Path) -> tuple[bytes, int, float]:
        raw, code, elapsed = super().execute(request, directory)
        parsed = OUTPUT_SCHEMA.validate_json(raw)
        result = parsed.get("result")
        frame = ProjectionFrame.model_validate(request.inputs["frame"])
        if not isinstance(result, dict) or result.get("row_ids") != list(frame.row_ids):
            raise CoastMASError("MODEL_OUTPUT_ERROR", "model output lost observation identity")
        field = "cluster" if request.handler == "ppci_mcdc" else "fitted"
        values = result.get(field)
        if not isinstance(values, list) or len(values) != len(frame.row_ids):
            raise CoastMASError("MODEL_OUTPUT_ERROR", "model output observation count differs")
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CoastMASError("MODEL_OUTPUT_ERROR", "model output contains nonnumeric values")
            if field == "cluster" and (
                value != int(value) or not 1 <= value <= float(str(request.parameters["clusters"]))
            ):
                raise CoastMASError("MODEL_OUTPUT_ERROR", "model output has invalid cluster labels")
        result["locations"] = frame.model_dump(mode="json")["locations"]
        result["observation_scope"] = frame.observation_scope
        result["joint_valid_cells"] = frame.joint_valid_cells
        result["business_validated"] = False
        output = json.dumps(parsed, allow_nan=False).encode()
        if len(output) > self.max_output_bytes:
            raise CoastMASError("MODEL_OUTPUT_ERROR", "enriched model output exceeds limit")
        return output, code, elapsed
