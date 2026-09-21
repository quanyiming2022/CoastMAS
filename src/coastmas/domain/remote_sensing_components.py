"""Trusted optical indices with explicit grids, masks and bounded result sizes."""

import numpy as np
from pydantic import JsonValue

from coastmas.core.contracts import SceneSpec, TargetGridSpec
from coastmas.core.errors import ConstraintError
from coastmas.core.numeric import FloatArray
from coastmas.domain.optical_observations import OpticalPair
from coastmas.domain.optical_preview import optical_preview
from coastmas.domain.remote_sensing import normalized_difference


def _index(
    context: dict[str, JsonValue],
    inputs: dict[str, JsonValue],
    positive: str,
    negative: str,
    name: str,
) -> dict[str, JsonValue]:
    scene = SceneSpec.model_validate(context.get("scene"))
    grid = TargetGridSpec.model_validate(scene.data_policy.get("target_grid"))
    left = np.asarray(inputs.get(positive), dtype=np.float64)
    right = np.asarray(inputs.get(negative), dtype=np.float64)
    if left.shape != (grid.height, grid.width) or left.size > 250000:
        raise ConstraintError("optical inputs must match the explicit grid, maximum 250000 cells")
    try:
        values = normalized_difference(left, right)
    except ValueError as exc:
        raise ConstraintError(str(exc)) from exc
    return _result(values, grid, name)


def _result(values: FloatArray, grid: TargetGridSpec, name: str) -> dict[str, JsonValue]:
    known = np.isfinite(values)
    rows: list[JsonValue] = [
        [float(value) if np.isfinite(value) else None for value in row] for row in values
    ]
    return {
        "index": rows,
        "preview": optical_preview(values, grid, name),
        "summary": {
            "index_name": name,
            "valid_pixels": int(known.sum()),
            "nodata_pixels": int((~known).sum()),
            "minimum": float(values[known].min()) if known.any() else None,
            "maximum": float(values[known].max()) if known.any() else None,
            "mean": float(values[known].mean()) if known.any() else None,
            "grid": grid.model_dump(mode="json"),
            "unit": "1",
            "method_scope": (
                "Optical spectral index; not validated land-cover classification or policy advice"
            ),
            "invalid_policy": (
                "nonfinite/negative reflectance and denominator <= 1e-8 remain NoData"
            ),
        },
    }


def vegetation_index(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    return _index(context, inputs, "nir", "red", "NDVI")


def water_index(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    return _index(context, inputs, "green", "nir", "NDWI")


def vegetation_change(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    scene = SceneSpec.model_validate(context.get("scene"))
    grid = TargetGridSpec.model_validate(scene.data_policy.get("target_grid"))
    pair = OpticalPair.model_validate(inputs.get("observations"))
    before, after = pair.frames
    if (
        before.grid != grid
        or before.acquired_at != scene.time_range.start
        or after.acquired_at != scene.time_range.end
    ):
        raise ConstraintError("scene grid and endpoints must match both actual acquisitions")
    previous = normalized_difference(
        np.asarray(before.nir, dtype=np.float64), np.asarray(before.red, dtype=np.float64)
    )
    current = normalized_difference(
        np.asarray(after.nir, dtype=np.float64), np.asarray(after.red, dtype=np.float64)
    )
    # Subtraction preserves NaN from either acquisition; no cloud filling or zero replacement.
    result = _result(current - previous, grid, "NDVI_CHANGE")
    summary = result["summary"]
    assert isinstance(summary, dict)
    summary["acquisitions"] = [
        frame.acquired_at.isoformat().replace("+00:00", "Z") for frame in pair.frames
    ]
    summary["source_items"] = [frame.source_item for frame in pair.frames]
    summary["method_scope"] = (
        "Two observed dates, joint valid pixels, later NDVI minus earlier NDVI; "
        "not a continuous trend, land-cover classification or causal attribution"
    )
    return result
