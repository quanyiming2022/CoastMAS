"""Bounded raster I/O: one global training sample and one fixed model application."""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

from coastmas.adapters.projection_pursuit import ProjectionFrame
from coastmas.core.contracts import UNITS

from .store import Problem


@dataclass(frozen=True)
class RasterInput:
    path: Path
    band: int
    name: str
    unit: str


@contextmanager
def aligned(variables):
    if not variables or len(variables) > 64:
        raise Problem(422, "VARIABLE_COUNT", "请选择1至64个有依据的栅格变量")
    with ExitStack() as stack:
        datasets = [stack.enter_context(rasterio.open(v.path)) for v in variables]
        first = datasets[0]
        if first.crs is None:
            raise Problem(422, "CRS_REQUIRED", "栅格缺少可信坐标参考系")
        if first.crs.is_geographic and not (
            -180 <= first.bounds.left <= first.bounds.right <= 180
            and -90 <= first.bounds.bottom <= first.bounds.top <= 90
        ):
            raise Problem(422, "CRS_BOUNDS_CONFLICT", "栅格坐标系与坐标范围冲突")
        for ds, variable in zip(datasets, variables, strict=True):
            if (
                ds.crs != first.crs
                or ds.transform != first.transform
                or ds.shape != first.shape
                or ds.tags().get("vertical_datum") != first.tags().get("vertical_datum")
            ):
                raise Problem(422, "GRID_MISMATCH", "输入网格不一致；不得静默重采样")
            if not 1 <= variable.band <= ds.count:
                raise Problem(422, "BAND_MISSING", "映射的波段不存在")
            try:
                source_unit = ds.units[variable.band - 1] or variable.unit
                UNITS.Quantity(0, source_unit).to(variable.unit)
            except Exception as exc:
                raise Problem(
                    422, "UNIT_INCOMPATIBLE", "文件单位不能保持量纲地适配到已认可变量单位"
                ) from exc
        yield datasets


def windows(dataset, size=256):
    for y in range(0, dataset.height, size):
        for x in range(0, dataset.width, size):
            yield Window(x, y, min(size, dataset.width - x), min(size, dataset.height - y))


def read_window(datasets, variables, window):
    physical = []
    valid = np.ones((int(window.height), int(window.width)), dtype=bool)
    for ds, variable in zip(datasets, variables, strict=True):
        raw = ds.read(variable.band, window=window, masked=True)
        mask = ~np.ma.getmaskarray(raw)
        values = (
            raw.data.astype(np.float64) * ds.scales[variable.band - 1]
            + ds.offsets[variable.band - 1]
        )
        if np.any(np.isinf(values[mask])):
            raise Problem(422, "NON_FINITE", "输入有效像元包含无限值")
        valid &= mask & np.isfinite(values)
        unit = ds.units[variable.band - 1] or variable.unit
        physical.append(np.asarray(UNITS.Quantity(values, unit).to(variable.unit).magnitude))
    return np.column_stack([p[valid] for p in physical]), valid


def training_frame(
    variables, *, scope, sample_size, seed, standardize, response_index, cancelled, window_size=256
):
    if scope not in {"all", "sample"} or (
        scope == "sample" and (not isinstance(sample_size, int) or not 4 <= sample_size <= 10000)
    ):
        raise Problem(422, "TRAINING_SCOPE", "明确完整训练或有界全域抽样训练范围")
    limit = sample_size if scope == "sample" else 10000
    chosen = np.empty((0, len(variables)))
    cells = np.empty((0, 2), dtype=np.int64)
    priorities = np.empty(0)
    rng = np.random.default_rng(seed)
    denominator = 0
    with aligned(variables) as datasets:
        first = datasets[0]
        for window in windows(first, window_size):
            if cancelled.is_set():
                raise Problem(409, "CANCELLED", "运行已取消")
            values, mask = read_window(datasets, variables, window)
            count = len(values)
            denominator += count
            if scope == "all" and denominator > limit:
                raise Problem(
                    422,
                    "TRAINING_BUDGET",
                    "完整原算法训练超过预算；必须明确采用一次全域抽样训练，不能逐块重训",
                )
            if not count:
                continue
            rows, columns = np.where(mask)
            identifiers = np.column_stack(
                (rows + int(window.row_off), columns + int(window.col_off))
            )
            chosen = np.concatenate((chosen, values))
            cells = np.concatenate((cells, identifiers))
            priorities = np.concatenate(
                (priorities, rng.random(count) if scope == "sample" else np.zeros(count))
            )
            if len(chosen) > limit:
                selected = np.argpartition(priorities, limit - 1)[:limit]
                chosen, cells, priorities = chosen[selected], cells[selected], priorities[selected]
        if denominator < 4:
            raise Problem(422, "OBSERVATIONS_REQUIRED", "至少需要四个共同有效观测")
        order = np.lexsort((cells[:, 1], cells[:, 0]))
        chosen, cells = chosen[order], cells[order]
        indices = [i for i in range(len(variables)) if i != response_index]
        x, y = rasterio.transform.xy(first.transform, cells[:, 0], cells[:, 1])
        lon, lat = Transformer.from_crs(
            first.crs, "EPSG:4326", always_xy=True, allow_ballpark=False
        ).transform(x, y, errcheck=True)
        frame = ProjectionFrame(
            row_ids=tuple(f"r{r}c{c}" for r, c in cells),
            feature_names=tuple(variables[i].name for i in indices),
            feature_units=tuple(variables[i].unit for i in indices),
            values=tuple(tuple(float(v) for v in row) for row in chosen[:, indices]),
            standardize=standardize,
            response=tuple(float(v) for v in chosen[:, response_index])
            if response_index is not None
            else None,
            response_unit=variables[response_index].unit if response_index is not None else None,
            locations=tuple(zip(lon, lat, strict=True)),
            observation_scope="sample_only" if scope == "sample" else "all_joint_valid_cells",
            joint_valid_cells=denominator,
        )
        return frame, {
            "training_scope": scope,
            "joint_valid_cells": denominator,
            "training_rows": len(chosen),
            "window_size": window_size,
            "sampling": "seeded uniform priorities over all jointly valid cells"
            if scope == "sample"
            else "all jointly valid cells",
            "crs": first.crs.to_string(),
            "transform": list(first.transform)[:6],
            "width": first.width,
            "height": first.height,
        }


def apply_raster(variables, model, output, *, classification, cancelled, window_size=256):
    predicted = 0
    minimum, maximum = np.inf, -np.inf
    with aligned(variables) as datasets:
        first = datasets[0]
        profile = first.profile.copy()
        profile.update(
            driver="GTiff",
            dtype="uint16" if classification else "float64",
            count=1,
            nodata=0 if classification else np.nan,
            tiled=True,
            blockxsize=256,
            blockysize=256,
            compress="deflate",
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(output, "w", **profile) as target:
            for window in windows(first, window_size):
                if cancelled.is_set():
                    raise Problem(409, "CANCELLED", "运行已取消")
                values, mask = read_window(datasets, variables, window)
                tile = np.full(
                    mask.shape,
                    0 if classification else np.nan,
                    dtype="uint16" if classification else "float64",
                )
                if len(values):
                    scores = np.asarray(model.predict(values), dtype=float)
                    if scores.shape != (len(values),) or not np.isfinite(scores).all():
                        raise Problem(422, "PREDICTION_INVALID", "原模型输出数量不匹配或非有限数")
                    if classification and (
                        np.any(scores != np.floor(scores))
                        or np.any(scores < 1)
                        or np.any(scores > 65535)
                    ):
                        raise Problem(422, "CLASSIFICATION_INVALID", "原模型类别编号不合法")
                    tile[mask] = scores
                    predicted += len(values)
                    minimum = min(minimum, float(scores.min()))
                    maximum = max(maximum, float(scores.max()))
                target.write(tile, 1, window=window)
            target.update_tags(
                application_scope="all_predictor_valid_cells",
                training="one_fixed_model",
                business_validated="false",
            )
    return {
        "predicted_cells": predicted,
        "application_scope": "all_predictor_valid_cells",
        "prediction_minimum": minimum if predicted else None,
        "prediction_maximum": maximum if predicted else None,
        "window_size": window_size,
    }
