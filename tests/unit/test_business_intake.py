"""Inspect supplied rasters without inferring scientific semantics or changing originals."""

import hashlib

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from coastmas.core.business_intake import inspect_directory


def raster(path, *, crs="EPSG:4326", transform=None, values=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=3,
        height=2,
        count=1,
        dtype="int8",
        crs=crs,
        transform=transform or from_origin(105, 32, 0.01, 0.01),
        nodata=-128,
    ) as target:
        target.write(
            np.array(values if values is not None else [[-128, 0, -1], [1, 2, 2]], dtype="int8"), 1
        )


def test_counts_categories_and_zero_but_does_not_invent_meaning(tmp_path):
    path = tmp_path / "AQ" / "qs_A.tif"
    raster(path)
    original = path.read_bytes()
    report = inspect_directory(tmp_path)
    row = report["rasters"][0]
    assert row["sha256"] == hashlib.sha256(original).hexdigest()
    assert row["statistics_scope"] == "full"
    assert row["valid_cells"] == 5 and row["nodata_cells"] == 1
    assert row["value_counts"] == [
        {"value": -1, "count": 1},
        {"value": 0, "count": 1},
        {"value": 1, "count": 1},
        {"value": 2, "count": 2},
    ]
    assert row["unit"] is None and row["observed_period"] is None
    assert "UNIT_UNDECLARED" in row["issues"]
    assert report["scientific_execution_ready"] is False
    assert path.read_bytes() == original


def test_mislabeled_geographic_crs_is_blocked_not_repaired(tmp_path):
    raster(tmp_path / "TN.tif", transform=from_origin(300000, 3500000, 1000, 1000))
    row = inspect_directory(tmp_path)["rasters"][0]
    assert "GEOGRAPHIC_BOUNDS_INVALID" in row["issues"]
    assert row["crs"] == "EPSG:4326"
    assert row["wgs84_bounds"] is None


def test_grid_identity_includes_origin_and_crs(tmp_path):
    raster(tmp_path / "a.tif")
    raster(tmp_path / "b.tif", transform=from_origin(105.001, 32, 0.01, 0.01))
    raster(tmp_path / "c.tif")
    rows = inspect_directory(tmp_path)["rasters"]
    assert rows[0]["grid_id"] == rows[2]["grid_id"]
    assert rows[0]["grid_id"] != rows[1]["grid_id"]


def test_large_raster_sample_never_claims_full_counts(tmp_path, monkeypatch):
    from coastmas.core import business_intake

    monkeypatch.setattr(business_intake, "FULL_SCAN_CELLS", 2)
    raster(tmp_path / "a.tif")
    row = inspect_directory(tmp_path)["rasters"][0]
    assert row["statistics_scope"] == "sample"
    assert row["valid_cells"] is None and row["nodata_cells"] is None
    assert row["value_counts"] == []


def test_does_not_follow_external_symlinks_or_execute_packages(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    raster(outside / "secret.tif")
    root = tmp_path / "source"
    root.mkdir()
    (root / "link.tif").symlink_to(outside / "secret.tif")
    package = root / "package"
    package.mkdir()
    (package / "DESCRIPTION").write_text(
        "Package: PPCI\nVersion: 0.1.5\n"
        "Title: Projection Pursuit for Cluster Identification\n"
        "License: GPL-3\nImports: Rcpp, RcppArmadillo, rARPACK\n"
    )
    (package / "bad.R").write_text('stop("must not run")')
    (package / "unsafe.dll").write_bytes(b"not executable")
    report = inspect_directory(root)
    assert report["rasters"] == []
    assert report["skipped_symlinks"] == ["link.tif"]
    assert report["models"][0]["method"] == "projection_pursuit_clustering"
    assert report["models"][0]["execution_status"] == "NOT_EXECUTABLE"


def test_corrupt_raster_is_reported_while_valid_files_survive(tmp_path):
    (tmp_path / "bad.tif").write_bytes(b"not a raster")
    raster(tmp_path / "good.tif")
    report = inspect_directory(tmp_path)
    assert len(report["errors"]) == 1 and len(report["rasters"]) == 1


def test_missing_input_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        inspect_directory(tmp_path / "missing")


def test_user_declarations_remain_distinct_from_file_measurements(tmp_path):
    from coastmas.core.business_intake import apply_declarations

    raster(tmp_path / "zhusanjiao" / "distance.tif")
    report = inspect_directory(tmp_path)
    declared = apply_declarations(
        report,
        {
            "year": 2022,
            "source": "开放网站",
            "use_restriction": "非商业使用",
            "units": {"zhusanjiao/": "m"},
        },
    )
    row = declared["rasters"][0]
    assert row["unit"] is None and row["declared_unit"] == "m"
    assert row["observed_period"] is None
    assert declared["user_declarations"]["year"] == 2022
    assert declared["scientific_execution_ready"] is False
    assert "UNIT_UNDECLARED" not in row["issues"]
    assert "UNIT_USER_DECLARED" in row["issues"]
    assert "UNIT_UNDECLARED" in report["rasters"][0]["issues"]


def test_cli_writes_private_report_without_overwriting_sources(tmp_path, monkeypatch):
    from scripts.inspect_business_sources import main

    source = tmp_path / "source"
    raster(source / "a.tif")
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["inspect", str(source), "--output", str(output)])
    assert main() == 0
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit):
        main()
