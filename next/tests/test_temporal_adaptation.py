"""Actual CF series: safe automatic choices, explicit assumptions, real numeric results."""

import io
import zipfile

import numpy as np
import pytest
from coastmas_next.worker import Worker
from netCDF4 import Dataset


def series(
    tmp_path,
    method="mean",
    *,
    axis_name="time",
    version="CF-1.12",
    values=(0, 2, 4),
    calendar="standard",
):
    path = tmp_path / "time-series.nc"
    with Dataset(path, "w") as ds:
        ds.Conventions = version
        ds.createDimension(axis_name, 3)
        ds.createDimension("nv", 2)
        time = ds.createVariable(axis_name, "f8", (axis_name,))
        time.units = "days since 2022-01-01"
        time.calendar = calendar
        time.standard_name = "time"
        time[:] = [0, 1, 2] if method == "point" else [0.5, 1.5, 2.5]
        if method != "point":
            time.bounds = "time_bounds"
            bounds = ds.createVariable("time_bounds", "f8", (axis_name, "nv"))
            bounds[:] = np.array([[0, 1], [1, 2], [2, 3]])
        variable = ds.createVariable("height", "f8", (axis_name,), fill_value=-9999)
        variable.units = "m"
        variable.standard_name = "sea_surface_height"
        variable.cell_methods = f"{axis_name}: {method}"
        variable[:] = values
    return path


def attach(workspace, path):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "CF actual adaptation", "purpose": "temporal"},
    ).json()
    reply = client.post(
        f"/api/projects/{project}/assets",
        files={"file": (path.name, path.read_bytes())},
        data={"task_id": task["id"], "expected_revision": 1},
    )
    assert reply.status_code == 201, reply.text
    return reply.json()["task"]


def save(client, task, options):
    task["draft"]["options"].update(options)
    response = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def execute(workspace, task):
    _, store, client, _ = workspace
    response = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "temporal"},
    )
    assert response.status_code == 202, response.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{response.json()['id']}/result")
    assert result.status_code == 200, result.text
    return result.json()["data"], response.json()["id"]


@pytest.mark.parametrize(
    "source,method,expected,version",
    [
        ("mean", "mean", 2, "CF-1.10"),
        ("sum", "sum", 6, "CF-1.12"),
        ("minimum", "min", 0, "CF-1.12"),
        ("maximum", "max", 4, "CF-1.12"),
    ],
)
def test_deterministic_file_choices_and_four_interval_methods(
    workspace, tmp_path, source, method, expected, version
):
    path = series(tmp_path, source, axis_name="t", version=version)
    task = attach(workspace, path)
    assert task["draft"]["options"]["variable"] == "height"
    assert task["draft"]["options"]["method"] == method
    assert task["draft"]["options"]["output_unit"] == "m"
    assert [m["field"] for m in task["draft"]["mapping"] if m["role"] == "feature"] == [
        "dataset/height"
    ]
    assert "start" not in task["draft"]["options"]  # target is a user goal, not file fact
    _, _, client, _ = workspace
    task = save(client, task, {"start": "2022-01-01", "end": "2022-01-04"})
    data, job = execute(workspace, task)
    assert data["value"] == expected
    assert data["observations"] == 3
    assert data["duration_unit"] == "days"
    assert data["time_axis_unit"] == "days since 2022-01-01"
    package = client.get(f"/api/jobs/{job}/bundle")
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert "temporal.csv" in archive.namelist()
        assert "temporal.csv-metadata.json" in archive.namelist()
        assert "height" in archive.read("temporal.csv").decode("utf-8-sig")


@pytest.mark.parametrize(
    "method,target,options,expected",
    [
        (
            "interpolation",
            "2022-01-01T12:00:00",
            {
                "adaptation_basis": (
                    "Engineering test only: linear change between these two observations"
                )
            },
            100,
        ),
        (
            "nearest",
            "2022-01-02T18:00:00",
            {
                "adaptation_basis": "Engineering test only: nearest within 0.3 days",
                "nearest_tolerance": 0.3,
            },
            400,
        ),
    ],
)
def test_point_methods_require_recorded_assumption_and_keep_used_observations(
    workspace, tmp_path, method, target, options, expected
):
    task = attach(workspace, series(tmp_path, "point"))
    assert not task["draft"]["options"].get("method")
    _, _, client, _ = workspace
    task = save(client, task, {"method": method, "target": target, "output_unit": "cm", **options})
    data, _ = execute(workspace, task)
    assert data["value"] == expected
    assert data["adaptation"]["basis"] == options["adaptation_basis"]
    assert data["adaptation"]["approximate"] is True
    assert data["source_observation_indices"] == ([0, 1] if method == "interpolation" else [2])


@pytest.mark.parametrize(
    "method,options,code",
    [
        (
            "point",
            {"method": "interpolation", "target": "2022-01-01T12:00:00"},
            "ADAPTATION_BASIS_REQUIRED",
        ),
        (
            "point",
            {"method": "interpolation", "target": "2021-12-31", "adaptation_basis": "test"},
            "OUTSIDE_TIME_RANGE",
        ),
        (
            "point",
            {
                "method": "nearest",
                "target": "2022-01-02T12:00:00",
                "nearest_tolerance": 1,
                "adaptation_basis": "test",
            },
            "NEAREST_TIE",
        ),
        (
            "point",
            {
                "method": "nearest",
                "target": "2022-01-02T18:00:00",
                "nearest_tolerance": 0.1,
                "adaptation_basis": "test",
            },
            "NEAREST_TOLERANCE",
        ),
        ("mean", {"start": "2022-01-01T12:00:00", "end": "2022-01-03"}, "PARTIAL_INTERVAL"),
        ("sum", {"start": "2022-01-01T12:00:00", "end": "2022-01-03"}, "PARTIAL_INTERVAL"),
        ("minimum", {"start": "2022-01-01T12:00:00", "end": "2022-01-03"}, "PARTIAL_INTERVAL"),
        ("mean", {"start": "2022-01-01", "end": "2022-01-05"}, "INCOMPLETE_TIME_COVERAGE"),
    ],
)
def test_only_dependent_preflight_is_blocked_without_enqueuing(
    workspace, tmp_path, method, options, code
):
    task = attach(workspace, series(tmp_path, method))
    _, _, client, _ = workspace
    task = save(client, task, options)
    check = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert check["ready"] is False
    assert any(issue["code"] == code for issue in check["issues"]), check
    assert client.get(f"/api/tasks/{task['id']}/jobs").json()["total"] == 0


def test_unknown_and_multistep_semantics_never_become_automatic_mean(workspace, tmp_path):
    path = series(tmp_path, "mean within days time: mean over days")
    task = attach(workspace, path)
    assert not task["draft"]["options"].get("method")
    _, _, client, _ = workspace
    task = save(
        client,
        task,
        {"variable": "height", "method": "mean", "start": "2022-01-01", "end": "2022-01-04"},
    )
    check = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert any(i["code"] == "TEMPORAL_MEANING" for i in check["issues"])


@pytest.mark.parametrize("attribute,value", [("unit", "kg"), ("concept", "unrelated_indicator")])
def test_manual_mapping_cannot_contradict_file_science(workspace, tmp_path, attribute, value):
    task = attach(workspace, series(tmp_path))
    _, _, client, _ = workspace
    task["draft"]["mapping"] = [
        {**b, attribute: value} if b["field"] == "dataset/height" else b
        for b in task["draft"]["mapping"]
    ]
    task = save(client, task, {"start": "2022-01-01", "end": "2022-01-04"})
    check = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert check["ready"] is False
    assert any(i["code"] == "FILE_BINDING_CONFLICT" for i in check["issues"]), check


@pytest.mark.parametrize("version", ["CF-1.7", "CF-1.8", "CF-1.9", "CF-1.11"])
def test_declared_cf_versions_use_actual_same_interval_semantics(workspace, tmp_path, version):
    task = attach(workspace, series(tmp_path, version=version))
    _, _, client, _ = workspace
    task = save(client, task, {"start": "2022-01-01", "end": "2022-01-04"})
    result, _ = execute(workspace, task)
    assert result["standard_version"] == version
    assert result["value"] == 2


def test_exact_point_needs_no_approximation_confirmation(workspace, tmp_path):
    task = attach(workspace, series(tmp_path, "point"))
    _, _, client, _ = workspace
    task = save(client, task, {"method": "interpolation", "target": "2022-01-02"})
    result, _ = execute(workspace, task)
    assert result["value"] == 2
    assert result["adaptation"]["approximate"] is False
    assert result["observations"] == 1


@pytest.mark.parametrize(
    "change,code",
    [
        ("masked_bounds", "TIME_BOUNDS_INVALID"),
        ("masked_value", "MISSING_OBSERVATION"),
        ("duplicate_axis", "TIME_AXIS_INVALID"),
        ("future_version", "CF_VERSION_UNSUPPORTED"),
    ],
)
def test_malformed_scientific_sources_are_rejected_before_execution(
    workspace, tmp_path, change, code
):
    path = series(tmp_path)
    with Dataset(path, "r+") as ds:
        if change == "masked_bounds":
            ds.variables["time_bounds"][0, 0] = np.ma.masked
        elif change == "masked_value":
            ds.variables["height"][1] = np.ma.masked
        elif change == "duplicate_axis":
            ds.variables["time"][:] = [0.5, 0.5, 2.5]
        else:
            ds.Conventions = "CF-1.99"
    task = attach(workspace, path)
    _, _, client, _ = workspace
    task = save(client, task, {"start": "2022-01-01", "end": "2022-01-04"})
    check = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert check["ready"] is False
    assert any(i["code"] == code for i in check["issues"]), check
