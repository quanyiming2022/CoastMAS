"""Independent file-level proof for the two explicit engineering raster evaluations.

No application computation helpers are imported. The supplied reference is a test
method, not a coastal scientific definition or validation data set.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(evidence_path, storage, source_path):
    browser = json.loads(evidence_path.read_text())
    assert sha(source_path) == browser["source"]["sha256"]
    reports = []
    for run, positive in [(browser["first_run"], True), (browser["second_run"], False)]:
        paths = list((storage / "results").glob(run + "-*.json"))
        assert len(paths) == 1
        result = json.loads(paths[0].read_text())
        config = result["manifest"]["method"]["spec"]["configuration"]
        assert config["method"] == "weighted"
        assert config["indicators"] == [
            {
                "concept": "distance",
                "unit": "m",
                "lower": 0,
                "upper": 1000000,
                "positive": positive,
                "weight": 1,
            }
        ]
        data = result["data"]
        files = data["files"]
        assert [f["role"] for f in files] == ["composite", "indicator", "contribution", "quality"]
        for f in files:
            p = storage / f["key"]
            assert p.stat().st_size == f["size"]
            assert sha(p) == f["sha256"]
        valid_count = 0
        mask_differences = 0
        maximum_error = 0.0
        minimum = float("inf")
        maximum = -float("inf")
        histogram = np.zeros(20, dtype="int64")
        with (
            rasterio.open(source_path) as src,
            rasterio.open(storage / files[0]["key"]) as output,
            rasterio.open(storage / files[-1]["key"]) as quality,
        ):
            assert (src.width, src.height, src.crs, src.transform) == (
                output.width,
                output.height,
                output.crs,
                output.transform,
            )
            assert output.units == ("1",)
            for row in range(0, src.height, 512):
                for col in range(0, src.width, 512):
                    window = Window(col, row, min(512, src.width - col), min(512, src.height - row))
                    raw = src.read(1, window=window, masked=True)
                    values = raw.data.astype("float64") * src.scales[0] + src.offsets[0]
                    valid = (~np.ma.getmaskarray(raw)) & np.isfinite(values)
                    actual = output.read(1, window=window, masked=True)
                    flags = quality.read(1, window=window)
                    mask_differences += int(
                        np.count_nonzero((~np.ma.getmaskarray(actual)) != valid)
                    ) + int(np.count_nonzero(flags != valid))
                    expected = values[valid] / 1000000
                    if not positive:
                        expected = 1 - expected
                    if len(expected):
                        maximum_error = max(
                            maximum_error, float(np.abs(actual.data[valid] - expected).max())
                        )
                        minimum = min(minimum, float(expected.min()))
                        maximum = max(maximum, float(expected.max()))
                        histogram += np.histogram(expected, bins=20, range=(0, 1))[0]
                    valid_count += int(valid.sum())
            assert mask_differences == 0
            assert maximum_error <= 1e-12
            assert data["statistics"]["total_pixels"] == src.width * src.height
            assert data["statistics"]["valid_pixels"] == valid_count
            assert data["statistics"]["histogram"]["counts"] == histogram.tolist()
            assert abs(data["statistics"]["minimum"] - minimum) < 1e-12
            assert abs(data["statistics"]["maximum"] - maximum) < 1e-12
            if positive:
                points = [browser["pixel"], *browser.get("additional_pixels", [])]
                for pixel in points:
                    assert pixel["sha256"] == files[0]["sha256"]
                    native = output.read(
                        1, window=Window(pixel["column"], pixel["row"], 1, 1), masked=True
                    )
                    native_valid = not bool(np.ma.getmaskarray(native)[0, 0])
                    assert pixel["valid"] == native_valid
                    if native_valid:
                        assert pixel["value"] == float(native[0, 0])
                    else:
                        assert pixel["value"] is None and pixel["status"] == "nodata"
                assert any(point["valid"] for point in points), "A native valid point is required"
        reports.append(
            {
                "run_id": run,
                "direction": "positive" if positive else "negative",
                "whole_grid_cells": data["statistics"]["total_pixels"],
                "valid_cells": valid_count,
                "mask_differences": mask_differences,
                "maximum_absolute_error": maximum_error,
                "all_output_bytes_hash_checked": True,
                "histogram_count_verified": True,
            }
        )
    return {
        "status": "PASS",
        "scope": "full_grid_independent_numerical_engineering_verification",
        "source_sha256": browser["source"]["sha256"],
        "runs": reports,
        "formal_business_validated": False,
        "limitation": (
            "Explicit engineering bounds and weights verify software, "
            "not ecological validity or independent scientific accuracy."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-evidence", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.browser_evidence, args.storage, args.source)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(
        json.dumps(
            {"status": result["status"], "runs": len(result["runs"]), "output": str(args.output)}
        )
    )
