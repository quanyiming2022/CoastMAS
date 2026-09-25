"""Actual supplied R implementations: fit once, predict chunks without refitting."""

import csv
import hashlib
import io
import json
import subprocess
import threading
from pathlib import Path

import numpy as np
from coastmas_next.stream_runtime import StreamModel

ROOT = Path(__file__).resolve().parents[1]


def test_actual_original_models_predict_same_training_rows_in_different_chunks(tmp_path):
    proof = json.loads((ROOT / "artifacts/provided-model-new-proof.json").read_text())
    image = proof["image"]
    raw = subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            image,
            "Rscript",
            "--vanilla",
            "-e",
            "write.csv(iris[,1:4],stdout(),row.names=FALSE)",
        ],
        text=True,
    )
    rows = list(csv.DictReader(io.StringIO(raw)))
    values = np.array([[float(v) for v in row.values()] for row in rows])
    for model, indices in [("ppci_mcdc", [0, 1, 2, 3]), ("ppr_ols", [1, 2, 3])]:
        x = values[:, indices]
        frame = {
            "row_ids": [f"iris-{i}" for i in range(150)],
            "feature_names": [f"x{i}" for i in indices],
            "feature_units": ["cm"] * len(indices),
            "values": x.tolist(),
            "standardize": False,
        }
        if model == "ppr_ols":
            frame.update(response=values[:, 0].tolist(), response_unit="cm")
        with StreamModel(
            image=image,
            handler=model,
            frame=frame,
            parameters={"size": 3 if model == "ppci_mcdc" else 2, "seed": 42},
            work_root=tmp_path,
            cancelled=threading.Event(),
        ) as runtime:
            actual = np.concatenate([runtime.predict(x[i : i + 17]) for i in range(0, len(x), 17)])
            assert runtime.result["fit_count"] == 1
            expected = np.asarray(
                proof["clustering" if model == "ppci_mcdc" else "regression"]["result"][
                    "cluster" if model == "ppci_mcdc" else "fitted"
                ]
            )
            if model == "ppci_mcdc":
                assert np.array_equal(actual[:, None] == actual, expected[:, None] == expected)
            else:
                assert np.max(np.abs(actual - expected)) < 1e-10
            assert runtime.result["training_rows"] == 150


def test_small_full_rasters_match_original_models_pixel_for_pixel(tmp_path):
    import rasterio
    from coastmas_next.spatial_model import RasterInput, apply_raster, training_frame
    from rasterio.transform import from_origin

    proof = json.loads((ROOT / "artifacts/provided-model-new-proof.json").read_text())
    raw = subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            proof["image"],
            "Rscript",
            "--vanilla",
            "-e",
            "write.csv(iris[,1:4],stdout(),row.names=FALSE)",
        ],
        text=True,
    )
    values = np.array(
        [[float(v) for v in row.values()] for row in csv.DictReader(io.StringIO(raw))]
    )
    variables = []
    for i in range(4):
        path = tmp_path / f"x{i}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=15,
            height=10,
            count=1,
            dtype="float64",
            crs="EPSG:4326",
            transform=from_origin(110, 23, 0.01, 0.01),
        ) as ds:
            ds.write(values[:, i].reshape(10, 15), 1)
            ds.set_band_unit(1, "cm")
        variables.append(RasterInput(path, 1, f"x{i}", "cm"))
    evidence = []
    for model, response_index in [("ppci_mcdc", None), ("ppr_ols", 0)]:
        frame, training = training_frame(
            variables,
            scope="all",
            sample_size=None,
            seed=42,
            standardize=False,
            response_index=response_index,
            cancelled=threading.Event(),
            window_size=4,
        )
        output = tmp_path / (model + ".tif")
        with StreamModel(
            image=proof["image"],
            handler=model,
            frame=frame.model_dump(mode="json"),
            parameters={"size": 3 if response_index is None else 2, "seed": 42},
            work_root=tmp_path,
            cancelled=threading.Event(),
        ) as runtime:
            applied = apply_raster(
                [v for i, v in enumerate(variables) if i != response_index],
                runtime,
                output,
                classification=response_index is None,
                cancelled=threading.Event(),
                window_size=4,
            )
            assert runtime.result["fit_count"] == 1
        with rasterio.open(output) as ds:
            actual = ds.read(1).ravel()
            assert np.all(ds.read_masks(1) > 0)
            assert ds.transform == rasterio.open(variables[0].path).transform
        expected = np.asarray(
            proof["clustering" if response_index is None else "regression"]["result"][
                "cluster" if response_index is None else "fitted"
            ]
        )
        error = float(np.max(np.abs(actual - expected)))
        assert error < 1e-10
        assert training["joint_valid_cells"] == applied["predicted_cells"] == 150
        evidence.append(
            {
                "model": model,
                "status": "PASS",
                "training_rows": 150,
                "full_domain_cells": 150,
                "max_abs_error": error,
                "fit_count": 1,
                "window_size": 4,
                "mask_and_grid": "PASS",
            }
        )
    encoded = json.dumps(
        {
            "scope": "technical iris test grid; not coastal scientific validation",
            "runner_sha256": hashlib.sha256((ROOT / "runtime/stream.R").read_bytes()).hexdigest(),
            "image": proof["image"],
            "models": evidence,
        },
        indent=2,
    ).encode()
    proof_directory = ROOT / "artifacts/model-verification"
    proof_directory.mkdir(exist_ok=True)
    target = proof_directory / (hashlib.sha256(encoded).hexdigest() + ".json")
    if target.exists():
        assert target.read_bytes() == encoded
    else:
        target.write_bytes(encoded)
