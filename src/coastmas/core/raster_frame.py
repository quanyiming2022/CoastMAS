"""Windowed, grid-identity-preserving preparation of explicit statistical observations.

Sampling never represents a full raster classification. Every selected row retains its
source cell and location; NoData exclusion and the complete joint denominator are recorded.
"""

from contextlib import ExitStack
from pathlib import Path
from typing import Literal, cast

import numpy as np
import rasterio  # type: ignore[import-untyped]
from pydantic import Field, JsonValue, StrictBool, model_validator
from pyproj import CRS, Transformer
from rasterio.windows import Window  # type: ignore[import-untyped]

from coastmas.adapters.projection_pursuit import ProjectionFrame
from coastmas.core.contracts import UNITS, Contract, Name
from coastmas.core.errors import ConstraintError


class RasterFeature(Contract):
    name: Name
    unit: Name
    band: int = Field(default=1, strict=True, ge=1)


class RasterFrameOptions(Contract):
    mode: Literal["all", "sample"]
    standardize: StrictBool
    sample_size: int = Field(default=1000, strict=True, ge=4, le=10000)
    seed: int = Field(default=42, strict=True, ge=0, le=2147483647)
    response_index: int | None = Field(default=None, strict=True, ge=0)

    @model_validator(mode="after")
    def no_implicit_sample(self) -> "RasterFrameOptions":
        if self.mode == "all" and (
            "sample_size" in self.model_fields_set or "seed" in self.model_fields_set
        ):
            raise ValueError("sample settings require explicit sample mode")
        return self


def prepare_raster_frame(
    paths: list[Path], features: list[RasterFeature], options: RasterFrameOptions
) -> dict[str, JsonValue]:
    if not 1 <= len(paths) == len(features) <= 8:
        raise ConstraintError("select between one and eight explicit raster variables")
    if len({item.name for item in features}) != len(features):
        raise ConstraintError("feature names must be unique")
    if options.response_index is not None and (
        options.response_index >= len(features) or len(features) < 2
    ):
        raise ConstraintError("response requires at least one distinct predictor")
    for feature in features:
        try:
            UNITS.parse_units(feature.unit)
        except Exception as exc:
            raise ConstraintError("each feature needs a recognized declared unit") from exc
    with ExitStack() as stack:
        datasets = [stack.enter_context(rasterio.open(path, driver="GTiff")) for path in paths]
        first = datasets[0]
        if first.crs is None:
            raise ConstraintError("source coordinates require a verified CRS")
        reference = CRS(first.crs)
        if reference.is_geographic and (
            first.bounds.left < -180
            or first.bounds.right > 180
            or first.bounds.bottom < -90
            or first.bounds.top > 90
        ):
            raise ConstraintError("source coordinates are outside geographic bounds")
        for dataset, feature in zip(datasets, features, strict=True):
            if (
                dataset.crs != first.crs
                or dataset.transform != first.transform
                or dataset.width != first.width
                or dataset.height != first.height
                or dataset.tags().get("vertical_datum") != first.tags().get("vertical_datum")
            ):
                raise ConstraintError("raster grid identity differs; explicitly align assets first")
            if feature.band > dataset.count:
                raise ConstraintError("selected raster band is absent")
            native = (
                dataset.units[feature.band - 1]
                or dataset.tags(feature.band).get("unit")
                or dataset.tags().get("unit")
            )
            if native and native != feature.unit:
                raise ConstraintError(
                    "declared unit differs from file; explicit conversion required"
                )
            if dataset.scales[feature.band - 1] != 1 or dataset.offsets[feature.band - 1] != 0:
                raise ConstraintError("physical scale/offset needs an explicit mapping")
        rng = np.random.default_rng(options.seed)
        limit = options.sample_size if options.mode == "sample" else 10000
        selected = np.empty((0, len(features)), dtype=np.float64)
        cells = np.empty((0, 2), dtype=np.int64)
        priorities = np.empty(0)
        valid = 0
        minimum, maximum = np.full(len(features), np.inf), np.full(len(features), -np.inf)
        # Fixed windows bound memory even for untiled TIFFs and large native blocks.
        for y in range(0, first.height, 512):
            for x in range(0, first.width, 512):
                window = Window(x, y, min(512, first.width - x), min(512, first.height - y))
                bands = [
                    dataset.read(feature.band, window=window, masked=True)
                    for dataset, feature in zip(datasets, features, strict=True)
                ]
                mask = np.ones(bands[0].shape, dtype=bool)
                for band in bands:
                    if np.any(np.isinf(band.compressed())):
                        raise ConstraintError("raster contains infinity")
                    mask &= ~np.ma.getmaskarray(band) & np.isfinite(band.data)
                rows, columns = np.where(mask)
                count = len(rows)
                valid += count
                if options.mode == "all" and valid > limit:
                    raise ConstraintError("more than 10000 observations; choose explicit sampling")
                if not count:
                    continue
                values = np.column_stack([band.data[mask] for band in bands]).astype(np.float64)
                minimum = np.minimum(minimum, values.min(axis=0))
                maximum = np.maximum(maximum, values.max(axis=0))
                identifiers = np.column_stack((rows + y, columns + x))
                keys = rng.random(count) if options.mode == "sample" else np.zeros(count)
                selected = np.concatenate((selected, values))
                cells = np.concatenate((cells, identifiers))
                priorities = np.concatenate((priorities, keys))
                if len(selected) > limit:
                    retained = np.argpartition(priorities, limit - 1)[:limit]
                    selected, cells, priorities = (
                        selected[retained],
                        cells[retained],
                        priorities[retained],
                    )
        if valid < 4:
            raise ConstraintError("at least four jointly valid observations are required")
        order = np.lexsort((cells[:, 1], cells[:, 0]))
        selected, cells = selected[order], cells[order]
        indices = [index for index in range(len(features)) if index != options.response_index]
        frame = ProjectionFrame(
            row_ids=tuple(f"r{row}c{column}" for row, column in cells),
            feature_names=tuple(features[index].name for index in indices),
            feature_units=tuple(features[index].unit for index in indices),
            values=tuple(tuple(float(value) for value in row) for row in selected[:, indices]),
            standardize=options.standardize,
            response=tuple(float(value) for value in selected[:, options.response_index])
            if options.response_index is not None
            else None,
            response_unit=features[options.response_index].unit
            if options.response_index is not None
            else None,
        )
        transform = first.transform
        xs = transform.a * (cells[:, 1] + 0.5) + transform.b * (cells[:, 0] + 0.5) + transform.c
        ys = transform.d * (cells[:, 1] + 0.5) + transform.e * (cells[:, 0] + 0.5) + transform.f
        longitude, latitude = Transformer.from_crs(
            reference, "EPSG:4326", always_xy=True, allow_ballpark=False, only_best=True
        ).transform(xs, ys, errcheck=True)
        locations = np.column_stack((longitude, latitude))
        if (
            not np.all(np.isfinite(locations))
            or np.any(np.abs(longitude) > 180)
            or np.any(np.abs(latitude) > 90)
        ):
            raise ConstraintError("transformed source coordinates are invalid")
        if reference.is_projected:
            support = max(
                float(np.hypot(transform.a, transform.d))
                * reference.axis_info[0].unit_conversion_factor,
                float(np.hypot(transform.b, transform.e))
                * reference.axis_info[1].unit_conversion_factor,
            )
        else:
            geod = reference.get_geod()
            if geod is None:
                raise ConstraintError("source CRS has no geodesic definition")
            _, _, horizontal = geod.inv(xs, ys, xs + transform.a, ys + transform.d)
            _, _, vertical = geod.inv(xs, ys, xs + transform.b, ys + transform.e)
            support = float(max(np.max(horizontal), np.max(vertical)))
        return {
            "frame": {
                **frame.model_dump(mode="json"),
                "locations": cast(JsonValue, locations.tolist()),
                "observation_scope": "sample_only"
                if options.mode == "sample"
                else "all_joint_valid_cells",
                "joint_valid_cells": valid,
            },
            "locations": cast(JsonValue, locations.tolist()),
            "quality": {
                "scope": "sample_only" if options.mode == "sample" else "all_joint_valid_cells",
                "joint_valid_cells": valid,
                "selected_cells": len(selected),
                "total_cells": first.width * first.height,
                "excluded_cells": first.width * first.height - valid,
                "mask_policy": "intersection_of_valid_cells",
                "minimum": cast(JsonValue, minimum.tolist()),
                "maximum": cast(JsonValue, maximum.tolist()),
                "statistics_scope": "full_joint_intersection",
                "sampling": "uniform_random_priority_without_replacement"
                if options.mode == "sample"
                else None,
                "seed": options.seed if options.mode == "sample" else None,
                "source_crs": reference.to_string(),
                "source_transform": list(first.transform)[:6],
                "shape": [first.height, first.width],
                "spatial_support_m": support,
                "spatial_support_definition": "maximum_selected_source_pixel_edge",
                "business_validated": False,
            },
        }
