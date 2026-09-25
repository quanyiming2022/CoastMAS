"""Task binding to one original model fit and optional complete raster application."""

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .models import ProjectionOptions, selected_bindings
from .spatial_model import RasterInput, aligned, apply_raster, training_frame
from .store import Problem
from .stream_runtime import RUNNER, StreamModel


class RasterMethod(ProjectionOptions):
    training_scope: Literal["all", "sample"]
    application_scope: Literal["sample", "full"]
    sample_size: int | None = Field(default=None, strict=True, ge=4, le=10000)

    @model_validator(mode="after")
    def explicit_sample(self):
        if self.training_scope == "sample" and self.sample_size is None:
            raise ValueError("sample training requires an explicit sample size")
        if self.training_scope == "all" and self.sample_size is not None:
            raise ValueError("all training must not carry an unused sample size")
        return self


def options(draft):
    keys = ["standardize", "size", "seed", "training_scope", "application_scope", "sample_size"]
    return RasterMethod.model_validate(
        {key: draft["options"][key] for key in keys if key in draft["options"]}
    )


def variables(settings, manifest):
    features, response = selected_bindings(manifest)
    if manifest["draft"]["purpose"] == "cluster" and len(features) < 2:
        raise Problem(422, "PPCI_FEATURES", "提供的PPCI实现需要至少两个解释变量")
    assets = {a["id"]: a for a in manifest["assets"]}
    result = []
    for index, binding in enumerate(features + response):
        asset = assets[binding["asset_id"]]
        if asset["facts"]["profile"] not in {"geotiff", "cog"}:
            raise Problem(422, "RASTER_VARIABLE", "栅格计算只能绑定实际栅格波段")
        field = next(
            f
            for layer in asset["facts"]["layers"]
            for f in layer["fields"]
            if layer["name"] + "/" + f["name"] == binding["field"]
        )
        result.append(
            RasterInput(
                settings.storage_root / asset["object_key"],
                field["band"],
                f"variable_{index + 1}",
                binding["unit"],
            )
        )
    return result, len(features) if response else None


def preflight(settings, manifest, release):
    method = options(manifest["draft"])
    if method.size < 2 and manifest["draft"]["purpose"] == "cluster":
        raise Problem(422, "MODEL_SIZE", "聚类至少需要两个类")
    if not release.runner_sha256 or not release.application_proof_sha256:
        raise Problem(422, "APPLICATION_UNVERIFIED", "此运行包尚未核验一次训练后的全域应用规则")
    if hashlib.sha256(RUNNER.read_bytes()).hexdigest() != release.runner_sha256:
        raise Problem(409, "RUNNER_CHANGED", "实际全域适配器与核验版本不一致")
    inputs, response = variables(settings, manifest)
    with aligned(inputs) as datasets:
        if method.training_scope == "all" and datasets[0].width * datasets[0].height > 10000:
            # Upper cell count is not the valid denominator: keep preflight permissive;
            # the worker counts jointly valid cells and rejects only the true budget excess.
            pass
    return method, inputs, response


def compute(settings, manifest, cancelled, artifact_dir, release):
    method, inputs, response_index = preflight(settings, manifest, release)
    frame, training = training_frame(
        inputs,
        scope=method.training_scope,
        sample_size=method.sample_size,
        seed=method.seed,
        standardize=method.standardize,
        response_index=response_index,
        cancelled=cancelled,
    )
    if method.size >= len(frame.values):
        raise Problem(422, "MODEL_SIZE", "模型规模必须小于训练观测数")
    with StreamModel(
        image=release.image,
        handler=release.model_id,
        frame=frame.model_dump(mode="json"),
        parameters={"size": method.size, "seed": method.seed},
        work_root=settings.storage_root / "work",
        cancelled=cancelled,
        runner_sha256=release.runner_sha256,
    ) as runtime:
        result = {
            "method": release.package,
            "runtime": manifest["runtime"],
            "row_ids": list(frame.row_ids),
            "locations": list(frame.locations),
            "observation_scope": frame.observation_scope,
            "joint_valid_cells": frame.joint_valid_cells,
            "training": training,
            "trained_model": runtime.result,
            "files": [],
            "business_validated": False,
        }
        fitted = runtime.result["fitted_values"]
        result["cluster" if response_index is None else "fitted"] = fitted
        if response_index is not None:
            result["response_unit"] = frame.response_unit
            result["residuals"] = [
                actual - fit for actual, fit in zip(frame.response, fitted, strict=True)
            ]
        if method.application_scope == "full":
            artifact_dir.mkdir(parents=True, exist_ok=False)
            path = artifact_dir / "prediction.tif"
            application = apply_raster(
                [variable for index, variable in enumerate(inputs) if index != response_index],
                runtime,
                path,
                classification=response_index is None,
                cancelled=cancelled,
            )
            digest = hashlib.sha256()
            with path.open("rb") as data:
                while chunk := data.read(1024**2):
                    digest.update(chunk)
            result["application"] = application
            result["files"] = [
                {
                    "name": path.name,
                    "key": str(path.relative_to(settings.storage_root)),
                    "sha256": digest.hexdigest(),
                    "size": path.stat().st_size,
                    "media_type": "image/tiff; application=geotiff",
                    "scope": "complete_predictor_valid_domain",
                }
            ]
        else:
            result["application"] = {
                "application_scope": "training_observations_only",
                "predicted_cells": len(frame.values),
            }
        result["runtime_diagnostics"] = runtime.diagnostics.decode(errors="replace")
        return result
