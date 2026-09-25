"""CF one-dimensional temporal adaptation with explicit interval/point semantics.

CF cell methods and calendars are file evidence. Approximation choices are user
intent, kept in the frozen task. Bounds, missingness and unsupported qualifiers
are validated before enqueue as well as at actual execution.
"""

import re

import cftime
import numpy as np
from netCDF4 import Dataset, date2num

from coastmas.core.contracts import UNITS

from .store import Problem

METHODS = {"mean": "mean", "sum": "sum", "minimum": "min", "maximum": "max", "point": None}
CALENDARS = {
    "standard",
    "gregorian",
    "proleptic_gregorian",
    "julian",
    "noleap",
    "365_day",
    "all_leap",
    "366_day",
    "360_day",
}
CF_VERSIONS = {"CF-1.7", "CF-1.8", "CF-1.9", "CF-1.10", "CF-1.11", "CF-1.12"}


def meaning(text, axis):
    match = re.fullmatch(
        r"\s*" + re.escape(axis) + r":\s*(mean|sum|minimum|maximum|point)\s*", text or ""
    )
    return match.group(1) if match else None


def candidates(facts):
    output = []
    coordinates = facts.get("coordinates", {})
    for layer in facts["layers"]:
        for field in layer["fields"]:
            dimensions = field.get("dimensions", [])
            if len(dimensions) != 1 or field["name"] == dimensions[0]:
                continue
            axis = coordinates.get(dimensions[0], {})
            method = meaning(field.get("cell_methods"), dimensions[0])
            if method is None or " since " not in axis.get("units", ""):
                continue
            output.append(
                {
                    "variable": field["name"],
                    "axis": dimensions[0],
                    "method": METHODS[method],
                    "cell_method": method,
                    "unit": field.get("unit"),
                    "calendar": axis.get("calendar", "standard"),
                    "time_axis_unit": axis["units"],
                }
            )
    return output


def automatic_choices(draft, asset):
    if (
        draft["purpose"] != "temporal"
        or asset["facts"]["profile"] != "netcdf"
        or len(draft["selection"]) != 1
    ):
        return
    options = draft["options"]
    available = candidates(asset["facts"])
    chosen = next((item for item in available if item["variable"] == options.get("variable")), None)
    if chosen is None and not options.get("variable") and len(available) == 1:
        chosen = available[0]
    if chosen is None:
        return
    automatic = {}
    for key, value in {
        "variable": chosen["variable"],
        "method": chosen["method"],
        "output_unit": chosen["unit"],
    }.items():
        if not options.get(key) and value is not None:
            options[key] = value
            automatic[key] = value
    if automatic:
        options["temporal_automatic"] = {
            "asset_id": asset["id"],
            "sha256": asset["sha256"],
            "file_choices": automatic,
        }
    for binding in draft["mapping"]:
        if binding["asset_id"] == asset["id"]:
            binding["role"] = (
                "feature" if binding["field"] == "dataset/" + chosen["variable"] else "ignored"
            )


def convert(value, source, target):
    try:
        converted = float(UNITS.Quantity(value, source).to(target).magnitude)
        if not np.isfinite(converted):
            raise ValueError("non-finite converted value")
        return converted
    except Exception as exc:
        raise Problem(
            422, "UNIT_INCOMPATIBLE", "单位不能确定性转换", {"source": source, "target": target}
        ) from exc


def date_coordinate(text, unit, calendar):
    if not isinstance(text, str):
        raise Problem(422, "TARGET_TIME_REQUIRED", "按源日历填写目标日期或时刻")
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?", text)
    if not match:
        raise Problem(
            422, "TARGET_TIME_REQUIRED", "日期格式为YYYY-MM-DD或YYYY-MM-DDTHH:MM:SS，按源日历解释"
        )
    parts = [int(value or 0) for value in match.groups()]
    try:
        return float(date2num(cftime.datetime(*parts, calendar=calendar), unit, calendar=calendar))
    except (ValueError, TypeError) as exc:
        raise Problem(422, "CALENDAR_DATE", "目标日期在源日历或源时间单位中无效") from exc


def numeric(variable, code, message):
    try:
        values = np.ma.asarray(variable[:], dtype=float)
    except (ValueError, TypeError) as exc:
        raise Problem(422, code, message) from exc
    return values


def compute(settings, manifest, cancelled):
    assets, options = manifest["assets"], manifest["draft"]["options"]
    if len(assets) != 1:
        raise Problem(422, "TEMPORAL_SOURCE", "请选择一个时间序列；多资料须明确关联规则")
    asset = assets[0]
    if asset["facts"]["profile"] != "netcdf":
        raise Problem(422, "TEMPORAL_MAPPING_REQUIRED", "表格序列尚需时间字段、日历和支撑映射")
    if cancelled.is_set():
        raise Problem(409, "CANCELLED", "运行已取消")
    with Dataset(settings.storage_root / asset["object_key"]) as ds:
        declared = set(re.findall(r"CF-[\d.]+", str(getattr(ds, "Conventions", ""))))
        if len(declared) != 1 or not declared.issubset(CF_VERSIONS):
            raise Problem(422, "CF_VERSION_UNSUPPORTED", "此适配档案需要明确的CF-1.7至CF-1.12声明")
        name = options.get("variable")
        if name not in ds.variables:
            raise Problem(422, "VARIABLE_REQUIRED", "请选择实际文件中的观测变量")
        variable = ds.variables[name]
        if variable.ndim != 1 or not 0 < variable.size <= 1_000_000:
            raise Problem(422, "TIME_SERIES_SCOPE", "此方法需要不超过100万条的一维时间变量")
        axis_name = variable.dimensions[0]
        axis = ds.variables.get(axis_name)
        if axis is None or not getattr(axis, "units", None) or axis_name == name:
            raise Problem(422, "TIME_AXIS_REQUIRED", "观测变量缺少实际时间轴与单位")
        calendar = getattr(axis, "calendar", "standard")
        if calendar not in CALENDARS or hasattr(axis, "climatology"):
            raise Problem(
                422, "CALENDAR_UNSUPPORTED", "此日历或气候态时间解释尚未接入，不能按普通年份猜算"
            )
        source_method = meaning(getattr(variable, "cell_methods", ""), axis_name)
        method = options.get("method")
        if source_method is None or method not in (
            {"nearest", "interpolation"} if source_method == "point" else {METHODS[source_method]}
        ):
            raise Problem(
                422,
                "TEMPORAL_MEANING",
                "目标方法与完整cell_methods不匹配；复杂修饰或多阶段统计需要明确适配",
            )
        unit = getattr(variable, "units", None)
        if not unit:
            raise Problem(422, "UNIT_REQUIRED", "观测变量缺少单位")
        target_unit = options.get("output_unit") or unit
        raw_times = numeric(axis, "TIME_AXIS_INVALID", "时间轴必须为数值")
        times = np.asarray(raw_times)
        if (
            raw_times.shape != (variable.size,)
            or np.ma.getmaskarray(raw_times).any()
            or not np.isfinite(times).all()
            or np.any(np.diff(times) <= 0)
        ):
            raise Problem(422, "TIME_AXIS_INVALID", "时间轴存在缺值、重复或非递增时刻")
        raw_values = numeric(variable, "VARIABLE_NUMERIC", "观测变量必须为数值")
        values = np.asarray(raw_values)
        valid = ~np.ma.getmaskarray(raw_values) & np.isfinite(values)
        common = {
            "variable": name,
            "method": method,
            "calendar": calendar,
            "calendar_basis": "file" if hasattr(axis, "calendar") else "CF_default_standard",
            "cell_methods": variable.cell_methods,
            "time_axis_unit": axis.units,
            "conversion": {"source_unit": unit, "target_unit": target_unit},
            "standard_version": next(iter(declared)),
        }
        if source_method == "point":
            target = date_coordinate(options.get("target"), axis.units, calendar)
            if not times[0] <= target <= times[-1]:
                raise Problem(422, "OUTSIDE_TIME_RANGE", "目标超出实际观测时间范围，不自动外推")
            exact = np.flatnonzero(np.isclose(times, target, rtol=0, atol=1e-10))
            basis = options.get("adaptation_basis")
            if not exact.size and (not isinstance(basis, str) or not basis.strip()):
                raise Problem(
                    422,
                    "ADAPTATION_BASIS_REQUIRED",
                    "最近邻或插值改变时间解释，请集中填写本次适配依据",
                )
            if exact.size:
                indices = [int(exact[0])]
                weights = [1.0]
            elif method == "nearest":
                tolerance = options.get("nearest_tolerance")
                if (
                    isinstance(tolerance, bool)
                    or not isinstance(tolerance, (int, float))
                    or not np.isfinite(tolerance)
                    or tolerance < 0
                ):
                    raise Problem(422, "NEAREST_TOLERANCE", "需要原时间单位下的非负容许偏差")
                distances = np.abs(times - target)
                nearest = np.flatnonzero(np.isclose(distances, distances.min(), rtol=0, atol=1e-10))
                if distances.min() > tolerance:
                    raise Problem(422, "NEAREST_TOLERANCE", "最近观测仍超过已声明容许偏差")
                if nearest.size > 1 and options.get("nearest_tie") not in {"earlier", "later"}:
                    raise Problem(
                        422, "NEAREST_TIE", "目标与两条观测等距，请明确采用较早或较晚观测"
                    )
                indices = [
                    int(nearest[-1] if options.get("nearest_tie") == "later" else nearest[0])
                ]
                weights = [1.0]
            else:
                right = int(np.searchsorted(times, target))
                indices = [right - 1, right]
                fraction = float((target - times[right - 1]) / (times[right] - times[right - 1]))
                weights = [1 - fraction, fraction]
            if not valid[indices].all():
                raise Problem(
                    422, "MISSING_OBSERVATION", "参与适配的实际观测缺测，不跨越缺测值插值"
                )
            value = float(np.dot(values[indices], weights))
            return {
                **common,
                "target": options["target"],
                "observations": len(indices),
                "value": convert(value, unit, target_unit),
                "scope": "declared_instant",
                "source_observation_indices": indices,
                "source_times": times[indices].tolist(),
                "adaptation": {
                    "approximate": not bool(exact.size),
                    "basis": basis if not exact.size else "exact_source_timestamp",
                    "weights": weights,
                    "nearest_tolerance": options.get("nearest_tolerance"),
                    "tie_choice": options.get("nearest_tie"),
                },
            }
        bound_name = getattr(axis, "bounds", None)
        if bound_name not in ds.variables:
            raise Problem(422, "TIME_BOUNDS_REQUIRED", "区间统计必须具有实际时间支撑边界")
        raw_bounds = numeric(
            ds.variables[bound_name], "TIME_BOUNDS_INVALID", "时间支撑边界必须为数值"
        )
        bounds = np.asarray(raw_bounds)
        if (
            bounds.shape != (variable.size, 2)
            or np.ma.getmaskarray(raw_bounds).any()
            or not np.isfinite(bounds).all()
            or np.any(bounds[:, 1] <= bounds[:, 0])
            or np.any(bounds[1:, 0] < bounds[:-1, 1])
        ):
            raise Problem(422, "TIME_BOUNDS_INVALID", "区间存在缺值、重叠或非递增边界")
        if np.any(times < bounds[:, 0]) or np.any(times > bounds[:, 1]):
            raise Problem(422, "TIME_BOUNDS_INVALID", "时间坐标不在所声明的观测支撑内")
        start, end = (
            date_coordinate(options.get(key), axis.units, calendar) for key in ("start", "end")
        )
        if end <= start:
            raise Problem(422, "TIME_ORDER", "目标结束必须晚于开始")
        overlap = np.maximum(0, np.minimum(bounds[:, 1], end) - np.maximum(bounds[:, 0], start))
        active = overlap > 0
        if not active.any():
            raise Problem(422, "NO_TIME_COVERAGE", "目标区间内没有实际观测支撑")
        covered = float(overlap.sum())
        if not np.isclose(covered, end - start, rtol=1e-12, atol=1e-10):
            raise Problem(
                422, "INCOMPLETE_TIME_COVERAGE", "实际支撑没有覆盖完整目标区间，不能默默跳过缺测"
            )
        if not np.allclose(
            overlap[active], (bounds[:, 1] - bounds[:, 0])[active], rtol=0, atol=1e-10
        ):
            raise Problem(
                422,
                "PARTIAL_INTERVAL",
                "目标截断原统计区间，无法从区间统计恢复部分时段；需要有依据的额外分配方法",
            )
        if not valid[active].all():
            raise Problem(422, "MISSING_OBSERVATION", "目标区间存在缺测，不自动忽略")
        if method == "mean":
            value = float(np.average(values[active], weights=overlap[active]))
        elif method == "sum":
            if not np.isclose(convert(0, unit, target_unit), 0):
                raise Problem(422, "OFFSET_SUM", "总量不能采用带偏移的单位转换")
            value = float(values[active].sum())
        elif method == "min":
            value = float(values[active].min())
        else:
            value = float(values[active].max())
        return {
            **common,
            "start": options["start"],
            "end": options["end"],
            "observations": int(active.sum()),
            "covered_duration": covered,
            "duration_unit": axis.units.split(" since ")[0],
            "value": convert(value, unit, target_unit),
            "scope": "declared_interval",
            "source_observation_indices": np.flatnonzero(active).tolist(),
            "adaptation": {"approximate": False, "basis": "complete_declared_source_intervals"},
        }
