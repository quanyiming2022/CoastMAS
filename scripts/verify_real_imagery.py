"""Independent raw-pixel cross-check of published real imagery results; no model helper reuse."""

import hashlib
import json
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from coastmas.adapters.geofiles import decode_geotiff
from coastmas.adapters.storage import ArtifactRecord
from coastmas.persistence.schema import ResultBundle
from coastmas.runtime_bootstrap import database_engine, object_store

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "artifacts/runtime/real-imagery/collection-1"


def bands(region):
    path = DIRECTORY / region
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["calibration_policy"] == "stac_matches_cog_v1"
    for filename, checksum in manifest["files"].items():
        assert hashlib.sha256((path / filename).read_bytes()).hexdigest() == checksum
    clear = np.isin(np.load(path / "scene-classification.npy", allow_pickle=False), [4, 5, 6])
    output = {}
    for name in ("red", "green", "nir"):
        calibration = manifest["band_calibration"][name]
        declared = calibration["stac"]
        assert declared["scale"] == calibration["file_scale"]
        assert declared["offset"] == calibration["file_offset"]
        assert declared["nodata"] == calibration["file_nodata"]
        raw = np.load(path / (name + "-raw.npy"), allow_pickle=False)
        physical = raw.astype("float64") * declared["scale"] + declared["offset"]
        physical[~clear | (raw == declared["nodata"])] = np.nan
        np.testing.assert_allclose(
            physical,
            decode_geotiff((path / (name + ".tif")).read_bytes()).values,
            rtol=0,
            atol=1e-12,
            equal_nan=True,
        )
        output[name] = physical
    return output


def ratio(first, second):
    valid = (
        np.isfinite(first)
        & np.isfinite(second)
        & (first >= 0)
        & (second >= 0)
        & (first + second > 1e-8)
    )
    output = np.full(first.shape, np.nan)
    output[valid] = (first[valid] - second[valid]) / (first[valid] + second[valid])
    return output


def main():
    report = json.loads((ROOT / "artifacts/runtime/real-imagery/demo-report.json").read_text())
    images = {
        name: bands(name) for name in ("yellow-river", "jiaozhou", "yangtze-2024", "yangtze-2025")
    }
    store = object_store()
    verified = {}
    with Session(database_engine()) as session:
        for key, trial in report["scenes"].items():
            result = session.get(ResultBundle, trial["result_id"])
            descriptor = result.manifest
            payload = json.loads(
                store.read(
                    ArtifactRecord(
                        descriptor["bucket"],
                        descriptor["key"],
                        descriptor["sha256"],
                        descriptor["size"],
                    )
                )
            )
            if key == "yangtze":
                window = payload["run_manifest"]["data_assets"][0]["quality"]["window"]
                row, column, height, width = (
                    window[k] for k in ("row", "column", "height", "width")
                )
                slices = (slice(row, row + height), slice(column, column + width))
                before, after = images["yangtze-2024"], images["yangtze-2025"]
                expected = ratio(after["nir"][slices], after["red"][slices]) - ratio(
                    before["nir"][slices], before["red"][slices]
                )
            else:
                image = images[key]
                expected = (
                    ratio(image["nir"], image["red"])
                    if key == "yellow-river"
                    else ratio(image["green"], image["nir"])
                )
            actual = np.asarray(payload["outputs"]["optical.index"], dtype="float64")
            np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12, equal_nan=True)
            summary = payload["outputs"]["optical.summary"]
            known = np.isfinite(expected)
            assert summary["valid_pixels"] == int(known.sum()) > 0
            assert summary["nodata_pixels"] == int((~known).sum())
            assert abs(summary["mean"] - float(expected[known].mean())) <= 1e-12
            assert payload["llm_calls"] == 0
            assert payload["run_manifest"]["scene"]["id"] == trial["scene_id"]
            verified[key] = {
                "status": "PASS",
                "result_id": result.id,
                "result_checksum": result.checksum,
                "max_abs_error": float(np.abs(actual[known] - expected[known]).max()),
                "valid_pixels": int(known.sum()),
                "nodata_pixels": int((~known).sum()),
                "valid_fraction": float(known.mean()),
                "mean": summary["mean"],
                "llm_calls": 0,
            }
    target = ROOT / "artifacts/research/real-imagery-crosscheck.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "method": "independent raw COG DN, calibration and pixelwise arithmetic",
                "absolute_tolerance": 1e-12,
                "scenes": verified,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(json.dumps(verified, ensure_ascii=False))


if __name__ == "__main__":
    main()
