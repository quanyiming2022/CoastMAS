"""Compare the pinned adapter with direct calls to the supplied R package implementations.

R's built-in iris is a technical fixture, never a substitute for coastal business validation.
"""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from pydantic import JsonValue

from coastmas.adapters.projection_pursuit import ProjectionPursuitAdapter
from coastmas.adapters.runtime import RunRequest

DIRECT = """set.seed(42)
x <- as.matrix(iris[,1:4])
c <- PPCI::mcdc(x, K=3, verb=0)$cluster
r <- pprRFA::zppr.numeric(iris$Sepal.Length, iris[,2:4], nterms=2, criteria="ols")
cat(jsonlite::toJSON(list(values=unname(x), clusters=as.integer(c),
fitted=as.numeric(predict(r$fit)), R=R.version.string,
packages=as.list(vapply(c("PPCI","pprRFA","Rcpp","RcppArmadillo","rARPACK","jsonlite","evd","nsRFA"),
function(p) as.character(packageVersion(p)), character(1)))), digits=16, auto_unbox=TRUE))"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker executable unavailable")
    adapter = ProjectionPursuitAdapter(image=args.image, docker=docker)
    direct = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cpus",
            "2",
            "--memory",
            "1g",
            "--pids-limit",
            "128",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            args.image,
            "/usr/bin/Rscript",
            "--vanilla",
            "-e",
            DIRECT,
        ],
        check=True,
        capture_output=True,
        timeout=120,
        text=True,
    )
    reference = json.loads(direct.stdout)
    values = reference["values"]
    common: dict[str, JsonValue] = {
        "row_ids": [f"iris-{i + 1}" for i in range(len(values))],
        "standardize": False,
    }
    with tempfile.TemporaryDirectory(prefix="coastmas-r-verification-") as temporary:
        cluster = adapter.run(
            RunRequest(
                handler="ppci_mcdc",
                inputs={
                    "frame": {
                        **common,
                        "feature_names": [
                            "sepal_length",
                            "sepal_width",
                            "petal_length",
                            "petal_width",
                        ],
                        "feature_units": ["cm"] * 4,
                        "values": values,
                    }
                },
                parameters={"clusters": 3, "seed": 42},
                work_root=Path(temporary),
                timeout_seconds=120,
            )
        )
        regression = adapter.run(
            RunRequest(
                handler="ppr_ols",
                inputs={
                    "frame": {
                        **common,
                        "feature_names": ["sepal_width", "petal_length", "petal_width"],
                        "feature_units": ["cm"] * 3,
                        "values": [row[1:] for row in values],
                        "response": [row[0] for row in values],
                        "response_unit": "cm",
                    }
                },
                parameters={"terms": 2, "seed": 42},
                work_root=Path(temporary),
                timeout_seconds=120,
            )
        )
    cluster_result, regression_result = (
        cluster.outputs.get("result"),
        regression.outputs.get("result"),
    )
    if not isinstance(cluster_result, dict) or not isinstance(regression_result, dict):
        raise AssertionError("adapter result must be an object")
    labels = np.asarray(cluster_result["cluster"])
    expected = np.asarray(reference["clusters"])
    if not np.array_equal(labels[:, None] == labels, expected[:, None] == expected):
        raise AssertionError("clustering differs from the original package")
    fitted = np.asarray(regression_result["fitted"])
    error = float(np.max(np.abs(fitted - np.asarray(reference["fitted"]))))
    if error > 1e-12:
        raise AssertionError("regression differs from the original package")
    if (
        cluster_result["row_ids"] != common["row_ids"]
        or regression_result["row_ids"] != common["row_ids"]
    ):
        raise AssertionError("adapter lost row identity")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(
            {
                "scope": "technical_iris_fixture_not_coastal_scientific_validation",
                "image": args.image,
                "runtime": reference["R"],
                "packages": reference["packages"],
                "clustering_pair_disagreements": 0,
                "regression_max_abs_error": error,
                "clustering": cluster.outputs,
                "regression": regression.outputs,
            },
            output,
            indent=2,
        )
    print(
        json.dumps(
            {
                "status": "PASS",
                "models": 2,
                "regression_max_abs_error": error,
                "evidence": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
